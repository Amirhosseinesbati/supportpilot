from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .domain import assess_return
from .graphs import ORDER_NUMBER, run_chat
from .knowledge import (
    activate_version,
    add_document,
    claim_next_job,
    invalidate_citations,
    process_job,
)
from .models import (
    Chunk,
    Conversation,
    Customer,
    Document,
    DocumentVersion,
    Event,
    GuestChallenge,
    IngestionJob,
    Message,
    Order,
    OrderLine,
    Product,
    ReturnRequest,
    Shipment,
    Ticket,
    User,
    Workspace,
    now,
    uid,
)
from .returns import ReturnConflict, record_return
from .review_graph import resume_review, start_review
from .security import (
    COOKIE_NAME,
    current_user,
    hash_password,
    issue_session,
    require_roles,
    revoke_session,
    verify_password,
)
from .tickets import TicketSyncError, TicketSyncInProgress, sync_ticket

logger = logging.getLogger("supportpilot")


def _worker(stop: threading.Event) -> None:
    while not stop.wait(0.8):
        try:
            with SessionLocal() as db:
                job = claim_next_job(db)
                if job:
                    process_job(db, job)
        except Exception:
            logger.exception("ingestion worker failure")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_mode.upper() not in {"DEMO", "CONNECTED"}:
        raise RuntimeError("APP_MODE must be DEMO or CONNECTED")
    if settings.connected and settings.secret_key == "local-demo-only-change-before-deployment":
        raise RuntimeError("CONNECTED mode needs a unique SECRET_KEY")
    if settings.database_url.startswith("sqlite"):
        Path("data").mkdir(exist_ok=True)
        Base.metadata.create_all(engine)
    settings.upload_root.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    thread = threading.Thread(target=_worker, args=(stop,), name="ingestion-worker", daemon=True)
    thread.start()
    yield
    stop.set()
    thread.join(timeout=2)


app = FastAPI(title="SupportPilot API", version="0.1.0", lifespan=lifespan)


class LoginBody(BaseModel):
    email: str
    password: str


class ConversationBody(BaseModel):
    subject: str = Field(default="New support conversation", max_length=200)


class MessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ReturnBody(BaseModel):
    order_id: str
    line_id: str
    quantity: int = Field(ge=1, le=100)
    condition: Literal["unopened", "opened", "damaged", "unknown"]
    reason: str = Field(min_length=3, max_length=1000)
    conversation_id: str | None = None


class ReviewBody(BaseModel):
    decision: Literal["approve", "edit", "reject", "expire"]
    version: str
    edited_reason: str | None = Field(default=None, max_length=1000)


class TicketReplyBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class TicketStatusBody(BaseModel):
    status: Literal["open", "resolved"]


class GuestChallengeBody(BaseModel):
    workspace_id: str
    order_number: str
    email: str


class GuestVerifyBody(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class CustomerSetupBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=256)


class ProductSetupBody(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    price_cents: int = Field(ge=0)


class ProductCategoryBody(BaseModel):
    category: str = Field(min_length=1, max_length=80)


class OrderLineSetupBody(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=1000)
    unit_price_cents: int = Field(ge=0)


class ShipmentSetupBody(BaseModel):
    status: Literal["pending", "in_transit", "delivered", "exception"]
    carrier: str | None = Field(default=None, max_length=80)
    tracking_code: str | None = Field(default=None, max_length=80)
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    promised_delivery_at: datetime | None = None


class OrderSetupBody(BaseModel):
    customer_id: str
    number: str = Field(min_length=2, max_length=40)
    placed_at: datetime
    status: Literal["pending", "in_transit", "delivered", "cancelled"]
    lines: list[OrderLineSetupBody] = Field(min_length=1)
    shipments: list[ShipmentSetupBody] = Field(default_factory=list)


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")


def _workspace(db: Session, user: User) -> Workspace:
    workspace = db.get(Workspace, user.workspace_id)
    if not workspace:
        raise _not_found()
    return workspace


def _user_payload(db: Session, user: User) -> dict:
    workspace = _workspace(db, user)
    return {"user": {"id": user.id, "email": user.email, "name": user.name,
                     "role": user.role, "workspace_id": user.workspace_id,
                     "customer_id": user.customer_id},
            "workspace": {"id": workspace.id, "name": workspace.name},
            "demo": not settings.connected}


def _customer_scope(user: User, customer_id: str) -> None:
    if user.role == "customer" and user.customer_id != customer_id:
        raise _not_found()


def _conversation(db: Session, user: User, conversation_id: str) -> Conversation:
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id,
                                                        Conversation.workspace_id == user.workspace_id))
    if not conversation:
        raise _not_found()
    _customer_scope(user, conversation.customer_id)
    return conversation


def _document(db: Session, user: User, document_id: str) -> Document:
    document = db.scalar(select(Document).where(Document.id == document_id,
                                                Document.workspace_id == user.workspace_id,
                                                Document.deleted_at.is_(None)))
    if not document:
        raise _not_found()
    return document


def _order(db: Session, user: User, order_id: str, customer_id: str | None = None) -> Order:
    query = select(Order).where(Order.id == order_id, Order.workspace_id == user.workspace_id)
    if customer_id:
        query = query.where(Order.customer_id == customer_id)
    order = db.scalar(query)
    if not order:
        raise _not_found()
    _customer_scope(user, order.customer_id)
    return order


def _order_payload(order: Order) -> dict:
    return {"id": order.id, "number": order.number, "status": order.status,
            "placed_at": order.placed_at, "total_cents": order.total_cents,
            "lines": [{"id": line.id, "product_id": line.product_id,
                       "product_name": line.product.name, "category": line.product.category,
                       "quantity": line.quantity, "unit_price_cents": line.unit_price_cents,
                       "returned_quantity": line.returned_quantity} for line in order.lines],
            "shipments": [{"id": shipment.id, "status": shipment.status,
                           "carrier": shipment.carrier, "tracking_code": shipment.tracking_code,
                           "shipped_at": shipment.shipped_at, "delivered_at": shipment.delivered_at,
                           "promised_delivery_at": shipment.promised_delivery_at}
                          for shipment in order.shipments]}


def _proposal_payload(proposal: ReturnRequest) -> dict:
    return {"id": proposal.id, "order_id": proposal.order_id, "line_id": proposal.line_id,
            "conversation_id": proposal.conversation_id, "status": proposal.status,
            "quantity": proposal.quantity, "condition": proposal.condition,
            "reason": proposal.reason, "policy_result": proposal.policy_result,
            "requires_review": proposal.requires_review, "version": proposal.version,
            "expires_at": proposal.expires_at, "created_at": proposal.created_at,
            "return_record_id": proposal.return_record.id if proposal.return_record else None}


def _document_payload(doc: Document) -> dict:
    return {"id": doc.id, "title": doc.title, "kind": doc.kind, "category": doc.category,
            "authority": doc.authority,
            "status": doc.status, "current_version": doc.current_version,
            "updated_at": doc.updated_at}


def _message_payload(message: Message) -> dict:
    return {"id": message.id, "role": message.role, "content": message.content,
            "citations": message.citations, "next_action": message.next_action,
            "missing_information": message.missing_information,
            "created_at": message.created_at}


def _ticket_payload(db: Session, ticket: Ticket) -> dict:
    conversation = db.get(Conversation, ticket.conversation_id)
    customer = db.get(Customer, conversation.customer_id) if conversation else None
    return {"id": ticket.id, "conversation_id": ticket.conversation_id,
            "subject": ticket.subject, "status": ticket.status, "summary": ticket.summary,
            "order_context": ticket.order_context,
            "external_ticket_id": ticket.external_ticket_id, "sync_status": ticket.sync_status,
            "evidence": ticket.evidence, "attempted_steps": ticket.attempted_steps,
            "unresolved_questions": ticket.unresolved_questions,
            "draft_response": ticket.draft_response,
            "customer_name": customer.name if customer else "Unknown",
            "updated_at": ticket.updated_at}


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "mode": settings.app_mode.upper(), "database": engine.dialect.name}


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower(), User.active.is_(True)))
    if not user or not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    issue_session(db, user, response)
    return _user_payload(db, user)


@app.get("/api/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _user_payload(db, user)


@app.get("/api/admin/customers")
def list_customer_accounts(user: User = Depends(require_roles("admin")),
                           db: Session = Depends(get_db)):
    rows = db.scalars(select(Customer).where(Customer.workspace_id == user.workspace_id)
                      .order_by(Customer.name).limit(500)).all()
    return {"items": [{"id": item.id, "name": item.name, "email": item.email} for item in rows]}


@app.post("/api/admin/customers")
def create_customer_account(body: CustomerSetupBody, user: User = Depends(require_roles("admin")),
                            db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Provide a valid email address")
    if settings.connected and len(body.password) < 16:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Connected customer passwords need at least 16 characters")
    if db.scalar(select(User.id).where(User.email == email)) or db.scalar(
        select(Customer.id).where(Customer.workspace_id == user.workspace_id,
                                  Customer.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Customer email already exists")
    customer = Customer(id=uid(), workspace_id=user.workspace_id,
                        name=body.name.strip(), email=email)
    account = User(id=uid(), workspace_id=user.workspace_id, customer_id=customer.id,
                   email=email, name=customer.name, role="customer",
                   password_hash=hash_password(body.password), active=True)
    db.add_all([customer, account])
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Customer email already exists") from error
    return {"id": customer.id, "name": customer.name, "email": customer.email,
            "user_id": account.id}


@app.get("/api/admin/products")
def list_products(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Product).where(Product.workspace_id == user.workspace_id)
                      .order_by(Product.name).limit(500)).all()
    return {"items": [{"id": item.id, "sku": item.sku, "name": item.name,
                       "category": item.category, "price_cents": item.price_cents} for item in rows]}


@app.post("/api/admin/products")
def create_product(body: ProductSetupBody, user: User = Depends(require_roles("admin")),
                   db: Session = Depends(get_db)):
    sku = body.sku.strip()
    category = _configured_category(body.category)
    if db.scalar(select(Product.id).where(Product.workspace_id == user.workspace_id,
                                          Product.sku == sku)):
        raise HTTPException(status.HTTP_409_CONFLICT, "SKU already exists")
    product = Product(id=uid(), workspace_id=user.workspace_id, sku=sku,
                      name=body.name.strip(), category=category,
                      price_cents=body.price_cents, specifications={})
    db.add(product)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "SKU already exists") from error
    return {"id": product.id, "sku": product.sku, "name": product.name,
            "category": product.category, "price_cents": product.price_cents}


def _configured_category(raw: str) -> str:
    category = raw.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", category) or category == "unclassified":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Configure a specific product category")
    return category


@app.patch("/api/admin/products/{product_id}")
def configure_product_category(product_id: str, body: ProductCategoryBody,
                               user: User = Depends(require_roles("admin")),
                               db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.id == product_id,
                                              Product.workspace_id == user.workspace_id))
    if product is None:
        raise _not_found()
    product.category = _configured_category(body.category)
    db.commit()
    return {"id": product.id, "sku": product.sku, "name": product.name,
            "category": product.category, "price_cents": product.price_cents}


@app.post("/api/admin/orders")
def create_local_order(body: OrderSetupBody, user: User = Depends(require_roles("admin")),
                       db: Session = Depends(get_db)):
    if settings.commerce_adapter != "local":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Local order creation is disabled when Shopify is the commerce source")
    customer = db.scalar(select(Customer).where(Customer.id == body.customer_id,
                                                 Customer.workspace_id == user.workspace_id))
    if customer is None:
        raise _not_found()
    if db.scalar(select(Order.id).where(Order.workspace_id == user.workspace_id,
                                        Order.number == body.number)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Order number already exists")
    products = {item.id: item for item in db.scalars(select(Product).where(
        Product.workspace_id == user.workspace_id,
        Product.id.in_([line.product_id for line in body.lines])))}
    if len(products) != len({line.product_id for line in body.lines}):
        raise _not_found()
    order = Order(id=uid(), workspace_id=user.workspace_id, customer_id=customer.id,
                  number=body.number.strip(), placed_at=body.placed_at, status=body.status,
                  total_cents=sum(line.quantity * line.unit_price_cents for line in body.lines))
    db.add(order)
    for line in body.lines:
        db.add(OrderLine(id=uid(), order_id=order.id, product_id=line.product_id,
                         quantity=line.quantity, unit_price_cents=line.unit_price_cents,
                         returned_quantity=0))
    for shipment in body.shipments:
        db.add(Shipment(id=uid(), order_id=order.id, status=shipment.status,
                        carrier=shipment.carrier, tracking_code=shipment.tracking_code,
                        shipped_at=shipment.shipped_at, delivered_at=shipment.delivered_at,
                        promised_delivery_at=shipment.promised_delivery_at))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Order number already exists") from error
    return _order_payload(order)


@app.post("/api/auth/logout")
def logout(response: Response, db: Session = Depends(get_db),
           raw: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    revoke_session(db, raw, response)
    return {"ok": True}


@app.get("/api/conversations")
def conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Conversation).where(Conversation.workspace_id == user.workspace_id)
    if user.role == "customer":
        query = query.where(Conversation.customer_id == user.customer_id)
    items = []
    for conversation in db.scalars(query.order_by(Conversation.updated_at.desc())):
        customer = db.get(Customer, conversation.customer_id)
        last = conversation.messages[-1] if conversation.messages else None
        items.append({"id": conversation.id, "subject": conversation.subject,
                      "status": conversation.status, "customer_name": customer.name if customer else "Unknown",
                      "updated_at": conversation.updated_at,
                      "last_message": last.content[:140] if last else "", "unread_count": 0})
    return {"items": items}


@app.post("/api/conversations")
def create_conversation(body: ConversationBody, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    if user.role != "customer" or not user.customer_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Customer account required")
    conversation = Conversation(id=uid(), workspace_id=user.workspace_id,
                                customer_id=user.customer_id, subject=body.subject,
                                status="open", updated_at=now())
    db.add(conversation)
    db.commit()
    return {"id": conversation.id, "subject": conversation.subject, "status": conversation.status}


@app.get("/api/conversations/{conversation_id}")
def conversation_detail(conversation_id: str, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    conversation = _conversation(db, user, conversation_id)
    customer = db.get(Customer, conversation.customer_id)
    if customer is None:
        raise _not_found()
    orders = db.scalars(select(Order).where(Order.workspace_id == user.workspace_id,
                                             Order.customer_id == conversation.customer_id)
                        .order_by(Order.placed_at.desc()).limit(5)).all()
    proposals = db.scalars(select(ReturnRequest).where(ReturnRequest.workspace_id == user.workspace_id,
        ReturnRequest.conversation_id == conversation.id).order_by(ReturnRequest.created_at.desc())).all()
    ticket = db.scalar(select(Ticket).where(Ticket.conversation_id == conversation.id,
                                           Ticket.workspace_id == user.workspace_id))
    events = db.scalars(select(Event).where(Event.conversation_id == conversation.id,
                                          Event.workspace_id == user.workspace_id)
                        .order_by(Event.created_at)).all()
    return {"id": conversation.id, "subject": conversation.subject, "status": conversation.status,
            "customer": {"id": customer.id, "name": customer.name, "email": customer.email},
            "messages": [_message_payload(message) for message in conversation.messages],
            "orders": [_order_payload(order) for order in orders],
            "proposals": [_proposal_payload(proposal) for proposal in proposals],
            "ticket": _ticket_payload(db, ticket) if ticket else None,
            "events": [{"id": event.id, "kind": event.kind, "detail": event.detail,
                        "created_at": event.created_at} for event in events]}


@app.post("/api/conversations/{conversation_id}/messages")
def post_message(conversation_id: str, body: MessageBody,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    conversation = _conversation(db, user, conversation_id)
    if user.role == "viewer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewer cannot send messages")
    message = Message(id=uid(), conversation_id=conversation.id,
                      role="customer" if user.role == "customer" else "operator",
                      content=body.content.strip(), citations=[], next_action="none",
                      missing_information=[], created_at=now())
    db.add(message)
    conversation.updated_at = now()
    db.commit()
    try:
        result = run_chat(workspace_id=user.workspace_id, conversation_id=conversation.id,
                          customer_id=conversation.customer_id, message_id=message.id,
                          question=message.content)
    except Exception as error:
        logger.exception("chat run failed", extra={"conversation_id": conversation.id, "message_id": message.id})
        db.add(Event(id=uid(), workspace_id=user.workspace_id, conversation_id=conversation.id,
                     kind="assistant_failed", detail={"message_id": message.id, "error": type(error).__name__}))
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Assistant unavailable; the customer message was saved. Retry or escalate.") from error
    assistant = Message(id=uid(), conversation_id=conversation.id, role="assistant",
                        content=result["answer"], citations=result.get("citations", []),
                        next_action=result.get("next_action", "none"),
                        missing_information=result.get("missing_information", []), created_at=now())
    db.add(assistant)
    for tool_event in result.get("tool_events", []):
        db.add(Event(id=uid(), workspace_id=user.workspace_id, conversation_id=conversation.id,
                     kind="tool_result", detail={"message_id": message.id, **tool_event}))
    conversation.updated_at = now()
    db.commit()
    return {"message": _message_payload(message), "assistant": _message_payload(assistant),
            "next_action": assistant.next_action,
            "missing_information": assistant.missing_information}


@app.post("/api/conversations/{conversation_id}/messages/stream")
def post_message_stream(conversation_id: str, body: MessageBody,
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    payload = post_message(conversation_id, body, user, db)
    answer = payload["assistant"]["content"]

    def events():
        yield f"event: message\ndata: {json.dumps(jsonable_encoder(payload['message']))}\n\n"
        for start in range(0, len(answer), 96):
            yield f"event: answer_chunk\ndata: {json.dumps({'text': answer[start:start + 96]})}\n\n"
        yield f"event: final\ndata: {json.dumps(jsonable_encoder(payload))}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/orders/{order_id}")
def order_detail(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _order_payload(_order(db, user, order_id))


@app.post("/api/guest/challenges")
def create_guest_challenge(body: GuestChallengeBody, db: Session = Depends(get_db)):
    if settings.connected:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED,
                            "A live verification channel must be configured for guests")
    customer = db.scalar(select(Customer).where(Customer.workspace_id == body.workspace_id,
                                                Customer.email == body.email.lower()))
    order = db.scalar(select(Order).where(Order.workspace_id == body.workspace_id,
                                           Order.number == body.order_number.upper(),
                                           Order.customer_id == customer.id)) if customer else None
    if not order:
        raise _not_found()
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = GuestChallenge(id=uid(), workspace_id=body.workspace_id,
                               order_id=order.id,
                               code_hash=hashlib.sha256((settings.secret_key + code).encode()).hexdigest(),
                               attempts=0, expires_at=now() + timedelta(minutes=5))
    db.add(challenge)
    db.commit()
    return {"challenge_id": challenge.id, "simulated_code": code,
            "notice": "Synthetic demo verification; no external message was sent"}


@app.post("/api/guest/challenges/{challenge_id}/verify")
def verify_guest_challenge(challenge_id: str, body: GuestVerifyBody,
                           db: Session = Depends(get_db)):
    if settings.connected:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Guest simulator is disabled")
    challenge = db.get(GuestChallenge, challenge_id)
    if not challenge or challenge.used_at or challenge.attempts >= 3 or \
            challenge.expires_at.replace(tzinfo=None) < now().replace(tzinfo=None):
        raise HTTPException(status.HTTP_410_GONE, "Challenge expired")
    challenge.attempts += 1
    digest = hashlib.sha256((settings.secret_key + body.code).encode()).hexdigest()
    if not secrets.compare_digest(challenge.code_hash, digest):
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect code")
    challenge.used_at = now()
    order = db.scalar(select(Order).where(Order.id == challenge.order_id,
                                         Order.workspace_id == challenge.workspace_id))
    if order is None:
        raise _not_found()
    db.commit()
    return {"verified": True, "order": _order_payload(order)}


@app.get("/api/documents")
def documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in {"admin", "operator", "viewer"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Staff access required")
    docs = db.scalars(select(Document).where(Document.workspace_id == user.workspace_id,
                                              Document.deleted_at.is_(None))
                      .order_by(Document.updated_at.desc())).all()
    jobs = db.scalars(select(IngestionJob).where(IngestionJob.workspace_id == user.workspace_id)
                      .order_by(IngestionJob.created_at.desc()).limit(30)).all()
    job_items = []
    for job in jobs:
        version = db.get(DocumentVersion, job.document_version_id)
        job_items.append({"id": job.id, "document_version_id": job.document_version_id,
                          "document_id": version.document_id if version else None,
                          "status": job.status, "progress": job.progress, "error": job.error,
                          "attempts": job.attempts, "cancel_requested": job.cancel_requested})
    return {"items": [_document_payload(doc) for doc in docs], "jobs": job_items}


async def _upload(db: Session, user: User, file: UploadFile, category: str,
                  authority: str | None = None,
                  document_id: str | None = None) -> dict:
    raw = await file.read(settings.max_upload_bytes + 1)
    try:
        doc, job = add_document(db, workspace_id=user.workspace_id, filename=file.filename or "",
                                raw=raw, category=category, authority=authority,
                                document_id=document_id)
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return {"document": _document_payload(doc), "job": {"id": job.id, "status": job.status}}


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...), category: str = Form("general"),
                          authority: str | None = Form(None),
                          user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return await _upload(db, user, file, category, authority)


@app.post("/api/documents/{document_id}/versions")
async def replace_document(document_id: str, file: UploadFile = File(...),
                           user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    doc = _document(db, user, document_id)
    return await _upload(db, user, file, doc.category, doc.authority, document_id)


@app.post("/api/documents/{document_id}/publish")
def publish_document(document_id: str, user: User = Depends(require_roles("admin")),
                     db: Session = Depends(get_db)):
    doc = _document(db, user, document_id)
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id,
                          DocumentVersion.version == doc.current_version))
    if not version or not db.scalar(select(Chunk.id).where(Chunk.document_version_id == version.id).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Complete ingestion before publishing")
    if doc.status == "published" and version.published_at:
        return _document_payload(doc)
    activate_version(db, doc, version)
    db.commit()
    return _document_payload(doc)


@app.post("/api/documents/{document_id}/retry")
def retry_document(document_id: str, user: User = Depends(require_roles("admin")),
                   db: Session = Depends(get_db)):
    doc = _document(db, user, document_id)
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                        .order_by(DocumentVersion.version.desc()).limit(1))
    if not version:
        raise _not_found()
    last = db.scalar(select(IngestionJob).where(IngestionJob.document_version_id == version.id)
                     .order_by(IngestionJob.created_at.desc()).limit(1))
    if last and last.status not in {"failed", "cancelled"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed or cancelled jobs may be retried")
    job = IngestionJob(id=uid(), workspace_id=user.workspace_id, document_version_id=version.id,
                       status="pending", progress=0)
    if doc.status != "published":
        doc.status = "processing"
    db.add(job)
    db.commit()
    return {"document": _document_payload(doc), "job": {"id": job.id, "status": job.status}}


@app.post("/api/ingestion-jobs/{job_id}/cancel")
def cancel_ingestion_job(job_id: str, user: User = Depends(require_roles("admin")),
                         db: Session = Depends(get_db)):
    job = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id,
                                                IngestionJob.workspace_id == user.workspace_id))
    if job is None:
        raise _not_found()
    if job.status == "cancelled":
        return {"id": job.id, "status": job.status, "cancel_requested": True}
    if job.status not in {"pending", "running"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only queued or running jobs can be cancelled")
    job.cancel_requested = True
    if job.status == "pending":
        job.status = "cancelled"
        job.error = "Ingestion cancelled"
        version = db.get(DocumentVersion, job.document_version_id)
        doc = db.get(Document, version.document_id) if version else None
        if doc and doc.status == "processing":
            doc.status = "draft"
    db.commit()
    return {"id": job.id, "status": job.status, "cancel_requested": True}


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str, user: User = Depends(require_roles("admin")),
                    db: Session = Depends(get_db)):
    doc = _document(db, user, document_id)
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)).all()
    invalidate_citations(db, [version.id for version in versions])
    for version in versions:
        version.published_at = None
    doc.deleted_at = now()
    doc.status = "deleted"
    db.commit()
    return {"ok": True}


@app.get("/api/documents/jobs/{job_id}/events")
def job_events(job_id: str, user: User = Depends(require_roles("admin", "operator", "viewer")),
               db: Session = Depends(get_db)):
    job = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id,
                                                IngestionJob.workspace_id == user.workspace_id))
    if not job:
        raise _not_found()
    def stream():
        for _ in range(120):
            with SessionLocal() as session:
                latest = session.get(IngestionJob, job_id)
                if not latest or latest.workspace_id != user.workspace_id:
                    break
                payload = {"status": latest.status, "progress": latest.progress, "error": latest.error}
                yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
                if latest.status in {"completed", "failed", "cancelled"}:
                    break
            time.sleep(1)
    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/sources/{chunk_id}")
def source_detail(chunk_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    chunk = db.scalar(select(Chunk).where(Chunk.id == chunk_id, Chunk.workspace_id == user.workspace_id))
    if not chunk:
        raise _not_found()
    version = db.get(DocumentVersion, chunk.document_version_id)
    doc = db.get(Document, version.document_id) if version else None
    if not version or not doc or doc.deleted_at or doc.status != "published" or not version.published_at:
        raise _not_found()
    return {"chunk_id": chunk.id, "document_title": doc.title, "version": version.version,
            "section": chunk.section, "page": chunk.page, "passage": chunk.content,
            "historical": doc.current_version != version.version,
            "effective_from": version.effective_from, "effective_to": version.effective_to}


@app.get("/api/proposals")
def proposals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(ReturnRequest).where(ReturnRequest.workspace_id == user.workspace_id)
    if user.role == "customer":
        query = query.where(ReturnRequest.customer_id == user.customer_id)
    return {"items": [_proposal_payload(item) for item in db.scalars(
        query.order_by(ReturnRequest.created_at.desc()).limit(100))]}


@app.post("/api/returns/proposals")
def create_return(body: ReturnBody, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    if user.role == "viewer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewer cannot propose returns")
    conversation = _conversation(db, user, body.conversation_id) if body.conversation_id else None
    if user.role != "customer" and conversation is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Staff proposals need a conversation")
    if user.role == "customer":
        customer_id = user.customer_id
    elif conversation is not None:
        customer_id = conversation.customer_id
    else:
        raise _not_found()
    if conversation and conversation.customer_id != customer_id:
        raise _not_found()
    order = _order(db, user, body.order_id, customer_id)
    line = db.scalar(select(OrderLine).where(OrderLine.id == body.line_id,
                                             OrderLine.order_id == order.id))
    if not line:
        raise _not_found()
    previous = db.scalar(select(ReturnRequest).where(ReturnRequest.workspace_id == user.workspace_id,
        ReturnRequest.customer_id == customer_id, ReturnRequest.order_id == order.id,
        ReturnRequest.line_id == line.id, ReturnRequest.status.in_(["pending_review", "recorded"]),
        ReturnRequest.condition == body.condition, ReturnRequest.quantity == body.quantity,
        ReturnRequest.reason == body.reason))
    if previous:
        return {"proposal": _proposal_payload(previous), "idempotent_replay": True}
    if line.product.category == "unclassified":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Configure product category before return eligibility")
    # Shipment rows have no line mapping in v1. Require the entire order to be delivered.
    all_delivered = bool(order.shipments) and all(
        shipment.status == "delivered" and shipment.delivered_at for shipment in order.shipments)
    delivered = min((s.delivered_at for s in order.shipments if s.delivered_at),
                    default=None) if all_delivered else None
    promised = next((s.promised_delivery_at for s in order.shipments if s.promised_delivery_at),
                    None) if len(order.shipments) == 1 else None
    late_days = max(0, (delivered.date() - promised.date()).days) if delivered and promised else 0
    workspace = _workspace(db, user)
    decision = assess_return(delivered_on=delivered.date() if delivered else None,
        requested_on=date.fromisoformat(settings.reference_date) if not settings.connected else date.today(),
        category=line.product.category, condition=body.condition,
        ordered_quantity=line.quantity, already_returned=line.returned_quantity,
        requested_quantity=body.quantity, late_delivery_days=late_days,
        policy=workspace.return_policy)
    policy = decision.__dict__
    version = hashlib.sha256(json.dumps({"order_id": order.id, "line_id": line.id,
        "quantity": body.quantity, "condition": body.condition, "reason": body.reason,
        "policy": policy}, sort_keys=True).encode()).hexdigest()
    proposal = ReturnRequest(id=uid(), workspace_id=user.workspace_id, customer_id=customer_id,
        conversation_id=body.conversation_id, order_id=order.id, line_id=line.id,
        quantity=body.quantity, condition=body.condition, reason=body.reason,
        policy_result=policy, status="pending_review" if decision.requires_review else
        ("denied" if not decision.eligible else "draft"),
        requires_review=decision.requires_review, version=version,
        expires_at=now() + timedelta(days=7))
    db.add(proposal)
    db.flush()
    if decision.eligible and not decision.requires_review:
        try:
            record_return(db, proposal)
        except ReturnConflict as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    db.add(Event(id=uid(), workspace_id=user.workspace_id, conversation_id=body.conversation_id,
                 kind="return_proposed", detail={"proposal_id": proposal.id, "policy": policy}))
    db.commit()
    if proposal.status == "pending_review":
        start_review(workspace_id=user.workspace_id, proposal_id=proposal.id, version=proposal.version)
    return {"proposal": _proposal_payload(proposal), "idempotent_replay": False}


@app.post("/api/proposals/{proposal_id}/review")
def review_proposal(proposal_id: str, body: ReviewBody,
                    user: User = Depends(require_roles("admin", "operator")),
                    db: Session = Depends(get_db)):
    proposal = db.scalar(select(ReturnRequest).where(ReturnRequest.id == proposal_id,
        ReturnRequest.workspace_id == user.workspace_id))
    if not proposal:
        raise _not_found()
    if proposal.status == "recorded" and body.decision == "approve" and body.version == proposal.version:
        return {"proposal": _proposal_payload(proposal), "idempotent_replay": True}
    try:
        result = resume_review(workspace_id=user.workspace_id, proposal_id=proposal.id,
            version=body.version, actor_id=user.id, decision=body.decision,
            edited_reason=body.edited_reason)
    except (ReturnConflict, ValueError, PermissionError) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except IntegrityError as error:
        db.rollback()
        current = db.scalar(select(ReturnRequest).where(ReturnRequest.id == proposal_id,
            ReturnRequest.workspace_id == user.workspace_id))
        if current and current.status == "recorded" and body.decision == "approve":
            return {"proposal": _proposal_payload(current), "idempotent_replay": True}
        raise HTTPException(status.HTTP_409_CONFLICT, "Concurrent review conflict; refresh") from error
    db.expire_all()
    current = db.scalar(select(ReturnRequest).where(ReturnRequest.id == proposal_id,
        ReturnRequest.workspace_id == user.workspace_id))
    if current is None:
        raise _not_found()
    if body.decision == "edit":
        start_review(workspace_id=user.workspace_id, proposal_id=proposal_id, version=current.version)
    return {"proposal": _proposal_payload(current),
            "idempotent_replay": result.get("idempotent_replay", False)}


@app.post("/api/conversations/{conversation_id}/escalate")
def escalate(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conversation = _conversation(db, user, conversation_id)
    existing = db.scalar(select(Ticket).where(Ticket.conversation_id == conversation.id,
                                               Ticket.workspace_id == user.workspace_id))
    if existing:
        return _ticket_payload(db, existing)
    messages = conversation.messages
    citations = [citation for message in messages for citation in message.citations]
    last_customer = next((m.content for m in reversed(messages) if m.role == "customer"), "")
    questions = [item for message in messages for item in message.missing_information]
    tool_events = db.scalars(select(Event).where(Event.workspace_id == user.workspace_id,
        Event.conversation_id == conversation.id, Event.kind == "tool_result")
        .order_by(Event.created_at.desc()).limit(100)).all()
    verified_ids = {item.detail["order_id"] for item in tool_events
                    if item.detail.get("tool") == "order_lookup" and item.detail.get("order_id")}
    mentioned_numbers = {match.group(0).upper() for item in messages
                         for match in ORDER_NUMBER.finditer(item.content)}
    related = db.scalars(select(Order).where(Order.workspace_id == user.workspace_id,
        Order.customer_id == conversation.customer_id,
        or_(Order.id.in_(verified_ids), Order.number.in_(mentioned_numbers)))
        .order_by(Order.placed_at.desc()).limit(3)).all()
    order_context = [jsonable_encoder(_order_payload(item)) for item in related]
    ticket = Ticket(id=uid(), workspace_id=user.workspace_id, conversation_id=conversation.id,
                    subject=conversation.subject, status="open", summary=last_customer[:1000] or conversation.subject,
                    order_context=order_context,
                    evidence=citations[-10:], attempted_steps=["Knowledge and scoped order lookup"],
                    unresolved_questions=questions[-10:], draft_response="")
    db.add(ticket)
    db.add(Event(id=uid(), workspace_id=user.workspace_id, conversation_id=conversation.id,
                 kind="ticket_created", detail={"ticket_id": ticket.id}))
    conversation.status = "escalated"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Ticket).where(Ticket.conversation_id == conversation.id,
                                                  Ticket.workspace_id == user.workspace_id))
        if existing:
            return _ticket_payload(db, existing)
        raise
    try:
        sync_ticket(db, ticket)
    except TicketSyncError as error:
        logger.warning("ticket connector needs reconciliation", extra={"ticket_id": ticket.id})
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    return _ticket_payload(db, ticket)


@app.post("/api/tickets/{ticket_id}/sync")
def ticket_sync(ticket_id: str, user: User = Depends(require_roles("admin", "operator")),
                db: Session = Depends(get_db)):
    ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id,
                                            Ticket.workspace_id == user.workspace_id))
    if not ticket:
        raise _not_found()
    try:
        sync_ticket(db, ticket)
    except TicketSyncInProgress as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except TicketSyncError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error
    return _ticket_payload(db, ticket)


@app.get("/api/tickets")
def tickets(user: User = Depends(require_roles("admin", "operator", "viewer")),
            db: Session = Depends(get_db)):
    rows = db.scalars(select(Ticket).where(Ticket.workspace_id == user.workspace_id)
                      .order_by(Ticket.updated_at.desc())).all()
    return {"items": [_ticket_payload(db, ticket) for ticket in rows]}


@app.post("/api/tickets/{ticket_id}/reply")
def ticket_reply(ticket_id: str, body: TicketReplyBody,
                 user: User = Depends(require_roles("admin", "operator")),
                 db: Session = Depends(get_db)):
    ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id,
                                            Ticket.workspace_id == user.workspace_id))
    if not ticket:
        raise _not_found()
    message = Message(id=uid(), conversation_id=ticket.conversation_id, role="operator",
                      content=body.content.strip(), citations=[], next_action="none",
                      missing_information=[], created_at=now())
    db.add(message)
    ticket.draft_response = body.content.strip()
    ticket.updated_at = now()
    db.add(Event(id=uid(), workspace_id=user.workspace_id, conversation_id=ticket.conversation_id,
                 kind="operator_reply", detail={"ticket_id": ticket.id, "message_id": message.id}))
    db.commit()
    return {"ticket": _ticket_payload(db, ticket), "message": _message_payload(message)}


@app.post("/api/tickets/{ticket_id}/status")
def ticket_status(ticket_id: str, body: TicketStatusBody,
                  user: User = Depends(require_roles("admin", "operator")),
                  db: Session = Depends(get_db)):
    ticket = db.scalar(select(Ticket).where(Ticket.id == ticket_id,
                                            Ticket.workspace_id == user.workspace_id))
    if not ticket:
        raise _not_found()
    ticket.status = body.status
    ticket.updated_at = now()
    db.add(Event(id=uid(), workspace_id=user.workspace_id, conversation_id=ticket.conversation_id,
                 kind="ticket_status", detail={"ticket_id": ticket.id, "status": body.status}))
    db.commit()
    return _ticket_payload(db, ticket)


@app.get("/api/connectors")
def connectors(user: User = Depends(require_roles("admin", "operator", "viewer"))):
    connected = settings.connected
    return {"items": [
        {"name": "Commerce simulator", "mode": "local", "status": "available", "detail": "Workspace-scoped orders and returns"},
        {"name": "Support simulator", "mode": "local", "status": "available", "detail": "Local tickets and replies"},
        {"name": "Shopify orders", "mode": "live", "status": "configured" if connected and settings.shopify_access_token and settings.shopify_shop_domain else "unconfigured", "detail": "Read-only order adapter"},
        {"name": "Zendesk tickets", "mode": "live", "status": "configured" if connected and settings.zendesk_api_token and settings.zendesk_subdomain else "unconfigured", "detail": "Ticket adapter"},
        {"name": "Model provider", "mode": "live" if connected else "fixture", "status": "configured" if connected and settings.openai_api_key else ("missing_credentials" if connected else "simulated"), "detail": settings.openai_model if connected else "Deterministic local fixture"},
    ]}


@app.get("/api/evaluations/summary")
def evaluation_summary(user: User = Depends(require_roles("admin", "operator", "viewer"))):
    directory = Path(__file__).resolve().parents[4] / "evals" / "results"
    latest = None
    for name in ("model_run.json", "fixture_validation.json"):
        path = directory / name
        if path.exists():
            latest = json.loads(path.read_text(encoding="utf-8"))
            break
    return {"dataset_count": 160, "latest_run": latest}
