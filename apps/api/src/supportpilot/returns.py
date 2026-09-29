from __future__ import annotations

import hashlib
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .domain import assess_return
from .models import (
    ActionLedger,
    Approval,
    Event,
    Order,
    OrderLine,
    ReturnRecord,
    ReturnRequest,
    User,
    Workspace,
    now,
    uid,
)


class ReturnConflict(Exception):
    pass


def record_return(db: Session, proposal: ReturnRequest) -> ReturnRecord:
    existing = db.scalar(select(ReturnRecord).where(ReturnRecord.proposal_id == proposal.id))
    if existing:
        return existing
    key = f"return:{proposal.workspace_id}:{proposal.id}"
    ledger = db.scalar(select(ActionLedger).where(ActionLedger.action_key == key).with_for_update())
    if ledger and ledger.status == "complete":
        record = db.scalar(select(ReturnRecord).where(ReturnRecord.proposal_id == proposal.id))
        if record:
            return record
        raise ReturnConflict("Completed ledger lacks a return record; reconcile before retry")
    if not ledger:
        ledger = ActionLedger(id=uid(), workspace_id=proposal.workspace_id, action_key=key,
                              status="claimed", request_payload={"proposal_id": proposal.id},
                              result_payload=None)
        db.add(ledger)
        db.flush()
    line = db.scalar(select(OrderLine).where(OrderLine.id == proposal.line_id,
                                             OrderLine.order_id == proposal.order_id).with_for_update())
    if not line or proposal.quantity > line.quantity - line.returned_quantity:
        raise ReturnConflict("Return quantity is no longer available")
    order = db.scalar(select(Order).where(Order.id == proposal.order_id,
                                          Order.workspace_id == proposal.workspace_id).with_for_update())
    workspace = db.get(Workspace, proposal.workspace_id)
    if not order or not workspace or line.product.category == "unclassified":
        raise ReturnConflict("Return details need operator reconciliation")
    all_delivered = bool(order.shipments) and all(
        shipment.status == "delivered" and shipment.delivered_at for shipment in order.shipments)
    delivered = min((item.delivered_at for item in order.shipments if item.delivered_at),
                    default=None) if all_delivered else None
    promised = next((item.promised_delivery_at for item in order.shipments
                     if item.promised_delivery_at), None) if len(order.shipments) == 1 else None
    late_days = max(0, (delivered.date() - promised.date()).days) if delivered and promised else 0
    current_policy = assess_return(
        delivered_on=delivered.date() if delivered else None,
        requested_on=date.today() if settings.connected else date.fromisoformat(settings.reference_date),
        category=line.product.category, condition=proposal.condition,
        ordered_quantity=line.quantity, already_returned=line.returned_quantity,
        requested_quantity=proposal.quantity, late_delivery_days=late_days,
        policy=workspace.return_policy)
    if not current_policy.eligible:
        raise ReturnConflict(f"Return eligibility changed: {current_policy.code}")
    record = ReturnRecord(id=uid(), workspace_id=proposal.workspace_id, proposal_id=proposal.id,
                          order_id=proposal.order_id, line_id=proposal.line_id,
                          quantity=proposal.quantity)
    db.add(record)
    proposal.return_record = record
    line.returned_quantity += proposal.quantity
    proposal.status = "recorded"
    ledger.status = "complete"
    ledger.result_payload = {"return_record_id": record.id}
    return record


def review_return(db: Session, *, workspace_id: str, proposal_id: str,
                  actor_id: str, decision: str, version: str,
                  edited_reason: str | None) -> tuple[ReturnRequest, bool]:
    actor = db.scalar(select(User).where(User.id == actor_id, User.workspace_id == workspace_id,
                                        User.role.in_(["admin", "operator"]), User.active.is_(True)))
    if not actor:
        raise PermissionError("Operator authorization is required")
    proposal = db.scalar(select(ReturnRequest).where(ReturnRequest.id == proposal_id,
        ReturnRequest.workspace_id == workspace_id).with_for_update())
    if not proposal:
        raise ReturnConflict("Proposal not found")
    if proposal.status == "recorded" and decision == "approve" and proposal.version == version:
        return proposal, True
    if proposal.status != "pending_review":
        raise ReturnConflict(f"Proposal is {proposal.status}")
    if proposal.version != version:
        raise ReturnConflict("Proposal changed; refresh before reviewing")
    if proposal.expires_at.replace(tzinfo=None) < now().replace(tzinfo=None):
        proposal.status = "expired"
        db.commit()
        raise ReturnConflict("Proposal expired")
    if decision == "edit":
        if not edited_reason or len(edited_reason.strip()) < 3:
            raise ReturnConflict("Edited reason is required")
        proposal.reason = edited_reason.strip()
        proposal.version = hashlib.sha256((proposal.version + proposal.reason).encode()).hexdigest()
    elif decision == "reject":
        proposal.status = "rejected"
    elif decision == "expire":
        proposal.status = "expired"
    elif decision == "approve":
        if not proposal.policy_result.get("eligible"):
            raise ReturnConflict("Policy does not allow this return")
        record_return(db, proposal)
    else:
        raise ReturnConflict("Unknown decision")
    db.add(Approval(id=uid(), workspace_id=workspace_id, proposal_id=proposal.id,
                    actor_id=actor_id, decision=decision,
                    proposal_version=version, note=edited_reason or ""))
    db.add(Event(id=uid(), workspace_id=workspace_id, conversation_id=proposal.conversation_id,
                 kind="return_reviewed", detail={"proposal_id": proposal.id,
                                                  "decision": decision, "status": proposal.status}))
    db.commit()
    return proposal, False
