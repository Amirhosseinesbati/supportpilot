"""Scoped, read-only Shopify order mirror for local support and return workflows."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .adapters import ConnectorError, LocalCommerceAdapter, OrderSnapshot
from .models import Order, OrderLine, Product, Shipment


def _id(workspace_id: str, kind: str, external_id: str) -> str:
    if not isinstance(external_id, str) or not external_id:
        raise ConnectorError(f"Shopify {kind} ID is missing")
    return str(uuid5(NAMESPACE_URL, f"supportpilot:shopify:{workspace_id}:{kind}:{external_id}"))


def _date(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError("Timestamp lacks timezone")
        return result
    except (TypeError, ValueError) as error:
        raise ConnectorError("Shopify returned an invalid timestamp") from error


def _sku(line: dict) -> str:
    raw = (line.get("sku") or "").strip()
    if raw and len(raw) <= 50:
        return raw
    key = raw or line["id"]
    return f"SHOPIFY-{hashlib.sha256(key.encode()).hexdigest()[:24]}"


def _local_snapshot(db: Session, workspace_id: str, customer_id: str,
                    order_number: str) -> OrderSnapshot:
    result = LocalCommerceAdapter(db).lookup_order(
        workspace_id=workspace_id, customer_id=customer_id, order_number=order_number)
    if not result:
        raise ConnectorError("Shopify mirror was not available after synchronization")
    return result


def mirror_shopify_order(db: Session, *, workspace_id: str, customer_id: str,
                         remote: OrderSnapshot) -> OrderSnapshot:
    """Mirror a verified order without changing Shopify or resetting local return counts."""
    if not remote.source_id or not remote.lines:
        raise ConnectorError("Shopify order has no complete line-item data")
    if len(remote.number) > 40 or remote.total_cents < 0:
        raise ConnectorError("Shopify order exceeds local storage bounds")
    order_id = _id(workspace_id, "order", remote.source_id)
    placed_at = _date(remote.placed_at)
    if placed_at is None:
        raise ConnectorError("Shopify order has no creation date")
    line_ids = [_id(workspace_id, "line", line["id"]) for line in remote.lines]
    shipment_ids = [_id(workspace_id, "shipment", item["id"]) for item in remote.shipments]
    if len(set(line_ids)) != len(line_ids) or len(set(shipment_ids)) != len(shipment_ids):
        raise ConnectorError("Shopify order contains duplicate resource IDs")

    existing_number = db.scalar(select(Order).where(Order.workspace_id == workspace_id,
                                                   Order.number == remote.number))
    if existing_number and existing_number.id != order_id:
        raise ConnectorError("Order number already belongs to another local source")
    order = db.get(Order, order_id)
    if order and (order.workspace_id != workspace_id or order.customer_id != customer_id):
        raise ConnectorError("Shopify order mirror belongs to a different verified customer")
    if order and any(line.id not in line_ids for line in order.lines):
        raise ConnectorError("Shopify order lines changed; reconcile existing local actions")
    if not order:
        order = Order(id=order_id, workspace_id=workspace_id, customer_id=customer_id,
                      number=remote.number, placed_at=placed_at, status=remote.status[:30],
                      total_cents=remote.total_cents)
        db.add(order)
        db.flush()
    else:
        order.placed_at = placed_at
        order.status = remote.status[:30]
        order.total_cents = remote.total_cents

    for item, line_id in zip(remote.lines, line_ids, strict=True):
        quantity = item["quantity"]
        if not isinstance(quantity, int) or quantity < 1:
            raise ConnectorError("Shopify line quantity is invalid")
        unit_price = item["unit_price_cents"]
        if not isinstance(unit_price, int) or unit_price < 0:
            raise ConnectorError("Shopify line price is invalid")
        sku = _sku(item)
        product = db.scalar(select(Product).where(Product.workspace_id == workspace_id,
                                                  Product.sku == sku))
        if not product:
            product = Product(id=_id(workspace_id, "product", sku),
                              workspace_id=workspace_id, sku=sku,
                              name=str(item["product_name"])[:200], category="unclassified",
                              price_cents=unit_price,
                              specifications={"source": "shopify", "external_sku": item.get("sku")})
            db.add(product)
            db.flush()
        line = db.get(OrderLine, line_id)
        if line:
            if line.order_id != order_id or line.returned_quantity > quantity:
                raise ConnectorError("Shopify line conflicts with recorded local returns")
            line.product_id = product.id
            line.quantity = quantity
            line.unit_price_cents = unit_price
        else:
            db.add(OrderLine(id=line_id, order_id=order_id, product_id=product.id,
                             quantity=quantity, unit_price_cents=unit_price,
                             returned_quantity=0))

    for item, shipment_id in zip(remote.shipments, shipment_ids, strict=True):
        shipment = db.get(Shipment, shipment_id)
        if shipment and shipment.order_id != order_id:
            raise ConnectorError("Shopify fulfillment conflicts with another order")
        if not shipment:
            shipment = Shipment(id=shipment_id, order_id=order_id)
            db.add(shipment)
        shipment.status = str(item["status"])[:30]
        shipment.carrier = str(item["carrier"])[:80] if item.get("carrier") else None
        shipment.tracking_code = str(item["tracking_code"])[:80] if item.get("tracking_code") else None
        shipment.shipped_at = _date(item.get("shipped_at"))
        shipment.delivered_at = _date(item.get("delivered_at"))
        shipment.promised_delivery_at = None  # Shopify estimate is not a promised policy date.
    for shipment in list(order.shipments):
        if shipment.id not in shipment_ids:
            db.delete(shipment)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        existing = db.get(Order, order_id)
        if existing and existing.workspace_id == workspace_id and existing.customer_id == customer_id:
            return replace(_local_snapshot(db, workspace_id, customer_id, remote.number),
                           source_id=remote.source_id)
        raise ConnectorError("Concurrent Shopify mirror conflict; retry lookup") from error
    return replace(_local_snapshot(db, workspace_id, customer_id, remote.number),
                   source_id=remote.source_id)
