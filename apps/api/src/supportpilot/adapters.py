from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Customer, Order


class ConnectorError(RuntimeError):
    pass


class AmbiguousWrite(ConnectorError):
    pass


@dataclass(frozen=True)
class OrderSnapshot:
    id: str
    number: str
    status: str
    placed_at: str
    shipments: list[dict]
    lines: list[dict]
    total_cents: int = 0
    source_id: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class CommercePort(Protocol):
    def lookup_order(self, *, workspace_id: str, customer_id: str,
                     order_number: str | None = None) -> OrderSnapshot | None: ...


class SupportPort(Protocol):
    def create_ticket(self, *, subject: str, body: str,
                      external_id: str) -> str: ...


class LocalSupportAdapter:
    """The local ticket is the simulator's provider record."""

    def create_ticket(self, *, subject: str, body: str, external_id: str) -> str:
        return external_id


class LocalCommerceAdapter:
    def __init__(self, db: Session):
        self.db = db

    def lookup_order(self, *, workspace_id: str, customer_id: str,
                     order_number: str | None = None) -> OrderSnapshot | None:
        query = select(Order).where(Order.workspace_id == workspace_id, Order.customer_id == customer_id)
        if order_number:
            query = query.where(Order.number == order_number)
        else:
            query = query.order_by(Order.placed_at.desc())
        order = self.db.scalar(query.limit(1))
        if not order:
            return None
        return OrderSnapshot(order.id, order.number, order.status, order.placed_at.isoformat(),
            [{"status": s.status, "carrier": s.carrier,
              "tracking_code": s.tracking_code,
              "delivered_at": s.delivered_at.isoformat() if s.delivered_at else None,
              "promised_delivery_at": s.promised_delivery_at.isoformat() if s.promised_delivery_at else None}
             for s in order.shipments],
            [{"id": line.id, "product_name": line.product.name,
              "category": line.product.category, "quantity": line.quantity,
              "returned_quantity": line.returned_quantity} for line in order.lines],
            total_cents=order.total_cents)


class ShopifyReadOnlyAdapter:
    """Read-only Admin GraphQL connector; identity always comes from local auth."""

    SHOP_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}\.myshopify\.com$")
    VERSION_RE = re.compile(r"^20\d\d-(01|04|07|10)$")
    ORDER_RE = re.compile(r"^#?[A-Za-z0-9][A-Za-z0-9_-]{2,39}$")
    ORDER_QUERY = """query Orders($q: String!) {
      orders(first: 5, query: $q) {
        edges { node {
          id name email createdAt displayFulfillmentStatus
          totalPriceSet { shopMoney { amount currencyCode } }
          lineItems(first: 100) {
            pageInfo { hasNextPage }
            edges { node {
              id title sku quantity
              originalUnitPriceSet { shopMoney { amount currencyCode } }
            } }
          }
          fulfillments(first: 100) {
            id displayStatus createdAt deliveredAt
            trackingInfo(first: 5) { company number }
          }
          fulfillmentsCount { count }
        } }
      }
    }"""

    def __init__(self, shop_domain: str, access_token: str, api_version: str = "2026-07",
                 client: httpx.Client | None = None, db: Session | None = None):
        if not self.SHOP_RE.fullmatch(shop_domain) or not self.VERSION_RE.fullmatch(api_version):
            raise ValueError("Invalid Shopify destination")
        self.shop_domain = shop_domain
        self.access_token = access_token
        self.api_version = api_version
        self.client = client or httpx.Client(timeout=12)
        self._owns_client = client is None
        self.db = db

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    @staticmethod
    def _cents(bag: dict) -> int:
        try:
            money = bag["shopMoney"]
            if money["currencyCode"] != "USD":
                raise ConnectorError("Shopify mirror currently requires USD shop currency")
            amount = Decimal(str(money["amount"])) * 100
            if not amount.is_finite() or amount != amount.to_integral_value() or amount < 0:
                raise ValueError("Amount is not a nonnegative number of cents")
            return int(amount)
        except (KeyError, TypeError, InvalidOperation, ValueError) as error:
            raise ConnectorError("Malformed Shopify money value") from error

    def _snapshot(self, node: dict) -> OrderSnapshot:
        try:
            line_connection = node["lineItems"]
            if line_connection["pageInfo"]["hasNextPage"]:
                raise ConnectorError("Shopify order has more than 100 lines; pagination is required")
            lines = []
            for edge in line_connection["edges"]:
                item = edge["node"]
                lines.append({"id": item["id"], "product_name": item["title"],
                              "sku": item.get("sku"), "quantity": int(item["quantity"]),
                              "unit_price_cents": self._cents(item["originalUnitPriceSet"])})
            fulfillments = node["fulfillments"]
            if len(fulfillments) < int(node["fulfillmentsCount"]["count"]):
                raise ConnectorError("Shopify order has more than 100 fulfillments; pagination is required")
            shipments = []
            for fulfillment in fulfillments:
                tracking = fulfillment["trackingInfo"]
                first_tracking = tracking[0] if tracking else {}
                shipments.append({"id": fulfillment["id"],
                                  "status": (fulfillment.get("displayStatus") or "unknown").lower(),
                                  "carrier": first_tracking.get("company"),
                                  "tracking_code": first_tracking.get("number"),
                                  "shipped_at": fulfillment["createdAt"],
                                  "delivered_at": fulfillment.get("deliveredAt"),
                                  "promised_delivery_at": None})
            return OrderSnapshot(node["id"], node["name"],
                node["displayFulfillmentStatus"].lower(), node["createdAt"], shipments,
                lines, total_cents=self._cents(node["totalPriceSet"]), source_id=node["id"])
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ConnectorError("Malformed Shopify order response") from error

    def lookup_verified(self, *, customer_email: str, order_number: str) -> OrderSnapshot | None:
        if not customer_email or not order_number or len(order_number) > 40 or not self.ORDER_RE.fullmatch(order_number):
            raise ValueError("Verified customer email and order number are required")
        query_text = f'name:"{order_number.lstrip("#")}"'
        url = f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"
        response = self.client.post(url, headers={"X-Shopify-Access-Token": self.access_token},
                                    json={"query": self.ORDER_QUERY, "variables": {"q": query_text}})
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise ConnectorError("Shopify GraphQL returned errors")
        try:
            edges = payload["data"]["orders"]["edges"]
        except (KeyError, TypeError) as error:
            raise ConnectorError("Malformed Shopify order response") from error
        for edge in edges:
            node = edge.get("node", {})
            if (str(node.get("email") or "").casefold() == customer_email.casefold()
                    and str(node.get("name") or "").lstrip("#").casefold()
                    == order_number.lstrip("#").casefold()):
                return self._snapshot(node)
        return None

    def lookup_order(self, *, workspace_id: str, customer_id: str,
                     order_number: str | None = None) -> OrderSnapshot | None:
        if not self.db or not order_number:
            return None
        customer = self.db.scalar(select(Customer).where(Customer.id == customer_id,
                                                        Customer.workspace_id == workspace_id))
        if not customer:
            return None
        return self.lookup_verified(customer_email=customer.email, order_number=order_number)


class ZendeskTicketAdapter:
    SUBDOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

    def __init__(self, subdomain: str, email: str, api_token: str,
                 client: httpx.Client | None = None):
        if not self.SUBDOMAIN_RE.fullmatch(subdomain):
            raise ValueError("Invalid Zendesk destination")
        self.base = f"https://{subdomain}.zendesk.com"
        self.auth = (f"{email}/token", api_token)
        self.client = client or httpx.Client(timeout=12)

    def find_ticket(self, external_id: str) -> str | None:
        response = self.client.get(f"{self.base}/api/v2/search.json",
                                   params={"query": f"type:ticket external_id:{external_id}"}, auth=self.auth)
        response.raise_for_status()
        for ticket in response.json().get("results", []):
            if ticket.get("external_id") == external_id:
                return str(ticket["id"])
        return None

    def create_ticket(self, *, subject: str, body: str, external_id: str) -> str:
        existing = self.find_ticket(external_id)
        if existing:
            return existing
        try:
            response = self.client.post(f"{self.base}/api/v2/tickets.json", auth=self.auth,
                headers={"Idempotency-Key": external_id},
                json={"ticket": {"subject": subject, "comment": {"body": body},
                                 "external_id": external_id}})
            response.raise_for_status()
            return str(response.json()["ticket"]["id"])
        except httpx.TimeoutException as error:
            raise AmbiguousWrite("Zendesk timed out; reconcile external_id before retry") from error


def commerce_for(db: Session) -> CommercePort:
    if settings.commerce_adapter == "local":
        return LocalCommerceAdapter(db)
    if settings.commerce_adapter == "shopify":
        if not settings.connected or not settings.shopify_shop_domain or not settings.shopify_access_token:
            raise ConnectorError("Shopify adapter selected without CONNECTED credentials")
        return ShopifyReadOnlyAdapter(settings.shopify_shop_domain,
                                       settings.shopify_access_token, settings.shopify_api_version,
                                       db=db)
    raise ConnectorError("Unknown commerce adapter")


def support_for() -> SupportPort:
    if settings.support_adapter == "local":
        return LocalSupportAdapter()
    if settings.support_adapter == "zendesk":
        if not settings.connected or not settings.zendesk_subdomain or not settings.zendesk_email or not settings.zendesk_api_token:
            raise ConnectorError("Zendesk adapter selected without CONNECTED credentials")
        return ZendeskTicketAdapter(settings.zendesk_subdomain, settings.zendesk_email,
                                    settings.zendesk_api_token)
    raise ConnectorError("Unknown support adapter")
