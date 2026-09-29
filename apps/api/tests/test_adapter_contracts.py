from __future__ import annotations

import json

import httpx
from langchain_core.messages import AIMessage
from sqlalchemy import func, select

from supportpilot.adapters import (
    AmbiguousWrite,
    OrderSnapshot,
    ShopifyReadOnlyAdapter,
    ZendeskTicketAdapter,
)
from supportpilot.commerce_sync import mirror_shopify_order
from supportpilot.config import settings
from supportpilot.db import SessionLocal
from supportpilot.graphs import (
    AnswerDraft,
    _clarify,
    _classify,
    _compose,
    _evaluate_action_policy,
    _lookup_order,
)
from supportpilot.models import ActionLedger, Customer, Order, Product, Ticket

from .conftest import login


def test_shopify_lookup_keeps_verified_email_and_exact_order_number():
    order_node = {
        "id": "gid://shopify/Order/731", "name": "NS-000001",
        "email": "customer@example.test", "createdAt": "2026-09-01T00:00:00Z",
        "displayFulfillmentStatus": "FULFILLED",
        "totalPriceSet": {"shopMoney": {"amount": "449.00", "currencyCode": "USD"}},
        "lineItems": {"pageInfo": {"hasNextPage": False}, "edges": [{"node": {
            "id": "gid://shopify/LineItem/900", "title": "Northstar Monitor",
            "sku": "NS-MON-001", "quantity": 1,
            "originalUnitPriceSet": {"shopMoney": {"amount": "449.00", "currencyCode": "USD"}},
        }}]},
        "fulfillments": [{"id": "gid://shopify/Fulfillment/600", "displayStatus": "DELIVERED",
                          "createdAt": "2026-09-20T00:00:00Z",
                          "deliveredAt": "2026-09-25T00:00:00Z",
                          "trackingInfo": [{"company": "Parcel Pilot", "number": "TRK-600"}]}],
        "fulfillmentsCount": {"count": 1},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "pilot.myshopify.com"
        assert request.url.path == "/admin/api/2026-07/graphql.json"
        assert request.headers["X-Shopify-Access-Token"] == "test-token"
        payload = json.loads(request.read())
        search = payload["variables"]["q"]
        assert 'name:"NS-000001"' in search
        assert "email:" not in search  # Email is verified from the returned order, not trusted as a search filter.
        assert "lineItems(first: 100)" in payload["query"]
        assert "fulfillments(first: 100)" in payload["query"]
        return httpx.Response(200, json={"data": {"orders": {"edges": [
            {"node": {**order_node, "id": "gid://shopify/Order/wrong",
                      "email": "other@example.test"}},
            {"node": order_node},
        ]}}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = ShopifyReadOnlyAdapter("pilot.myshopify.com", "test-token", client=client)
    found = adapter.lookup_verified(customer_email="customer@example.test", order_number="NS-000001")
    assert found and found.id == "gid://shopify/Order/731"
    assert found.lines[0]["sku"] == "NS-MON-001"
    assert found.shipments[0]["tracking_code"] == "TRK-600"
    assert adapter.lookup_verified(customer_email="absent@example.test", order_number="NS-000001") is None


def test_shopify_mirror_is_scoped_stable_and_supports_local_return(client):
    node = {
        "id": "gid://shopify/Order/990001", "name": "NS-990001",
        "email": "ns.customer.0001@example.test", "createdAt": "2026-09-10T00:00:00Z",
        "displayFulfillmentStatus": "FULFILLED",
        "totalPriceSet": {"shopMoney": {"amount": "449.00", "currencyCode": "USD"}},
        "lineItems": {"pageInfo": {"hasNextPage": False}, "edges": [{"node": {
            "id": "gid://shopify/LineItem/990001", "title": "Northstar Monitor 001",
            "sku": "NS-MON-001", "quantity": 1,
            "originalUnitPriceSet": {"shopMoney": {"amount": "449.00", "currencyCode": "USD"}},
        }}]},
        "fulfillments": [{"id": "gid://shopify/Fulfillment/990001",
                          "displayStatus": "DELIVERED", "createdAt": "2026-09-16T00:00:00Z",
                          "deliveredAt": "2026-09-25T00:00:00Z",
                          "trackingInfo": [{"company": "Parcel Pilot", "number": "TRK-990001"}]}],
        "fulfillmentsCount": {"count": 1},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert json.loads(request.read())["variables"]["q"] == 'name:"NS-990001"'
        return httpx.Response(200, json={"data": {"orders": {"edges": [{"node": node}]}}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with SessionLocal() as db:
        adapter = ShopifyReadOnlyAdapter("pilot.myshopify.com", "test-token", client=http, db=db)
        remote = adapter.lookup_order(workspace_id="ws_northstar",
                                      customer_id="cust_ns_demo_001", order_number="NS-990001")
        assert remote is not None
        first = mirror_shopify_order(db, workspace_id="ws_northstar",
                                     customer_id="cust_ns_demo_001", remote=remote)
        again = mirror_shopify_order(db, workspace_id="ws_northstar",
                                     customer_id="cust_ns_demo_001", remote=remote)
        assert first.id == again.id and first.lines[0]["id"] == again.lines[0]["id"]
        assert first.source_id == node["id"]
        assert first.shipments[0]["status"] == "delivered"
        product = db.scalar(select(Product).where(Product.workspace_id == "ws_northstar",
                                                  Product.sku == "NS-MON-001"))
        assert product and product.category == "monitor"
        assert db.scalar(select(Order).where(Order.id == first.id)).customer_id == "cust_ns_demo_001"
        other = db.scalar(select(Customer).where(Customer.workspace_id == "ws_northstar",
                                                 Customer.id != "cust_ns_demo_001"))
        assert other is not None
        assert adapter.lookup_order(workspace_id="ws_northstar",
                                    customer_id=other.id, order_number="NS-990001") is None
        order_id = first.id
        line_id = first.lines[0]["id"]
    login(client, "ns.customer.0001@example.test")
    response = client.post("/api/returns/proposals", json={"order_id": order_id,
        "line_id": line_id, "quantity": 1, "condition": "unopened",
        "reason": "Return a verified Shopify monitor"})
    assert response.status_code == 200, response.text
    assert response.json()["proposal"]["status"] == "recorded"


def test_unknown_shopify_sku_needs_admin_category_before_return(client):
    external_id = "gid://shopify/Order/990002"
    remote = OrderSnapshot(id=external_id, number="NS-990002", status="fulfilled",
        placed_at="2026-09-10T00:00:00Z", total_cents=32000, source_id=external_id,
        lines=[{"id": "gid://shopify/LineItem/990002", "product_name": "New display",
                "sku": "UNMAPPED-990002", "quantity": 1, "unit_price_cents": 32000}],
        shipments=[{"id": "gid://shopify/Fulfillment/990002", "status": "delivered",
                    "carrier": "Parcel Pilot", "tracking_code": "TRK-990002",
                    "shipped_at": "2026-09-16T00:00:00Z",
                    "delivered_at": "2026-09-25T00:00:00Z", "promised_delivery_at": None}])
    with SessionLocal() as db:
        local = mirror_shopify_order(db, workspace_id="ws_northstar",
                                     customer_id="cust_ns_demo_001", remote=remote)
        product = db.scalar(select(Product).where(Product.workspace_id == "ws_northstar",
                                                  Product.sku == "UNMAPPED-990002"))
        assert product and product.category == "unclassified"
        product_id = product.id
    body = {"order_id": local.id, "line_id": local.lines[0]["id"],
            "quantity": 1, "condition": "unopened", "reason": "New display return"}
    login(client, "ns.customer.0001@example.test")
    blocked = client.post("/api/returns/proposals", json=body)
    assert blocked.status_code == 422
    assert "category" in blocked.text.lower()
    client.post("/api/auth/logout")
    login(client, "admin.ns@example.test")
    configured = client.patch(f"/api/admin/products/{product_id}", json={"category": "monitor"})
    assert configured.status_code == 200, configured.text
    client.post("/api/auth/logout")
    login(client, "ns.customer.0001@example.test")
    allowed = client.post("/api/returns/proposals", json=body)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["proposal"]["status"] == "recorded"


def test_chat_shopify_lookup_materializes_custom_prefix_order(seeded_database, monkeypatch):
    node = {
        "id": "gid://shopify/Order/990003", "name": "WEB-990003",
        "email": "ns.customer.0001@example.test", "createdAt": "2026-09-10T00:00:00Z",
        "displayFulfillmentStatus": "FULFILLED",
        "totalPriceSet": {"shopMoney": {"amount": "449.00", "currencyCode": "USD"}},
        "lineItems": {"pageInfo": {"hasNextPage": False}, "edges": [{"node": {
            "id": "gid://shopify/LineItem/990003", "title": "Northstar Monitor",
            "sku": "NS-MON-001", "quantity": 1,
            "originalUnitPriceSet": {"shopMoney": {"amount": "449.00", "currencyCode": "USD"}},
        }}]},
        "fulfillments": [{"id": "gid://shopify/Fulfillment/990003",
                          "displayStatus": "DELIVERED", "createdAt": "2026-09-16T00:00:00Z",
                          "deliveredAt": "2026-09-25T00:00:00Z", "trackingInfo": []}],
        "fulfillmentsCount": {"count": 1},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.read())["variables"]["q"] == 'name:"WEB-990003"'
        return httpx.Response(200, json={"data": {"orders": {"edges": [{"node": node}]}}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("supportpilot.graphs.commerce_for", lambda db: ShopifyReadOnlyAdapter(
        "pilot.myshopify.com", "test-token", client=http, db=db))
    state = {"workspace_id": "ws_northstar", "customer_id": "cust_ns_demo_001",
             "question": "Where is my order WEB-990003?"}
    assert _classify(state)["intent"] == "order"
    found = _lookup_order({**state, "intent": "order"})
    assert found["order"]["number"] == "WEB-990003"
    assert found["order"]["source_id"] == node["id"]
    assert found["order"]["lines"][0]["category"] == "monitor"
    with SessionLocal() as db:
        assert db.scalar(select(Order).where(Order.id == found["order"]["id"])) is not None


def test_shopify_split_delivery_uses_earliest_date_without_late_exception(seeded_database):
    result = _evaluate_action_policy({
        "intent": "return", "workspace_id": "ws_northstar", "as_of": "2026-09-27",
        "question": "Return one Northstar Monitor unopened",
        "order": {
            "source_id": "gid://shopify/Order/990004",
            "lines": [{"id": "line-990004", "product_name": "Northstar Monitor",
                       "category": "monitor", "quantity": 1, "returned_quantity": 0}],
            "shipments": [
                {"status": "delivered", "delivered_at": "2026-08-26T00:00:00Z",
                 "promised_delivery_at": "2026-08-01T00:00:00Z"},
                {"status": "delivered", "delivered_at": "2026-09-25T00:00:00Z",
                 "promised_delivery_at": "2026-09-01T00:00:00Z"},
            ],
        },
    })
    assert result["policy_result"] == "ineligible"
    assert result["policy_reason"] == "return_window_elapsed"


def test_local_partial_delivery_does_not_claim_return_eligibility(seeded_database):
    result = _evaluate_action_policy({
        "intent": "return", "workspace_id": "ws_northstar", "as_of": "2026-09-27",
        "question": "Return one Northstar Monitor unopened",
        "order": {
            "lines": [{"id": "local-line", "product_name": "Northstar Monitor",
                       "category": "monitor", "quantity": 1, "returned_quantity": 0}],
            "shipments": [
                {"status": "delivered", "delivered_at": "2026-09-25T00:00:00Z"},
                {"status": "in_transit", "delivered_at": None},
            ],
        },
    })
    assert result["policy_result"] == "delivery_unverified"
    assert result["missing_information"] == ["Delivery confirmation for every shipment"]


def test_connected_model_budget_and_usage_signal(monkeypatch):
    captured = {}

    class Model:
        usage = {"input_tokens": 812, "output_tokens": 71, "total_tokens": 883}
        metadata = {}

        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def with_structured_output(self, schema, **kwargs):
            assert schema is AnswerDraft
            assert kwargs == {"include_raw": True}
            return self

        def invoke(self, messages):
            captured["messages"] = messages
            return {"raw": AIMessage(content="", usage_metadata=Model.usage,
                                      response_metadata=Model.metadata),
                "parsed": AnswerDraft(answer="The source is incomplete."),
                "parsing_error": None}

    monkeypatch.setattr("supportpilot.graphs.ChatOpenAI", Model)
    monkeypatch.setattr(settings, "app_mode", "CONNECTED")
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    source_text = "SENSITIVE_SOURCE_TEXT " * 2000
    state = {"intent": "knowledge", "question": "Q" * 6000,
             "order": {"internal_note": "SENSITIVE_ORDER_TEXT " * 1000},
             "passages": [{"chunk_id": "chunk-1", "document_title": "Manual",
                           "version": 1, "section": "Returns", "page": 1,
                           "passage": source_text, "score": 1.0,
                           "category": "returns", "authority": "official_policy",
                           "effective_from": None}], "tool_events": []}
    response = _compose(state)
    event = response["tool_events"][-1]
    assert captured["kwargs"]["max_completion_tokens"] == settings.model_max_output_tokens == 700
    assert captured["kwargs"]["max_retries"] == 0
    human_input = captured["messages"][1].content
    assert len(human_input) <= settings.model_max_input_chars == 16000
    assert len(human_input.split("Scoped order: ", 1)[0]) <= 4011
    assert len(human_input.split("Scoped order: ", 1)[1].split("\nEvidence:", 1)[0]) <= 3000
    assert len(human_input.split("Evidence:\n", 1)[1]) <= settings.model_max_passage_chars + 200
    assert event["usage_status"] == "known"
    assert (event["input_tokens"], event["output_tokens"], event["total_tokens"]) == (812, 71, 883)
    assert event["cost_status"] == "unknown" and event["cost_usd"] is None
    assert event["context_truncated"] is True
    assert "SENSITIVE_SOURCE_TEXT" not in json.dumps(event)
    assert "SENSITIVE_ORDER_TEXT" not in json.dumps(event)
    Model.usage = None
    unknown = _compose(state)["tool_events"][-1]
    assert unknown["usage_status"] == "unknown"
    assert unknown["input_tokens"] is None and unknown["total_tokens"] is None
    assert unknown["cost_status"] == "unknown" and unknown["cost_usd"] is None
    Model.metadata = {"token_usage": {"prompt_tokens": 100, "completion_tokens": 20,
                                       "total_tokens": 120}}
    fallback = _compose(state)["tool_events"][-1]
    assert fallback["usage_status"] == "known"
    assert (fallback["input_tokens"], fallback["output_tokens"], fallback["total_tokens"]) == (100, 20, 120)
    no_call = _clarify({"next_action": "clarify", "missing_information": ["A verified source"]})
    assert no_call["tool_events"][-1]["model_called"] is False
    assert no_call["tool_events"][-1]["cost_usd"] == 0
    monkeypatch.setattr(settings, "app_mode", "DEMO")
    assert "tool_events" not in _clarify({"next_action": "clarify", "missing_information": []})


def test_zendesk_reconciles_external_id_and_marks_timeout_ambiguous():
    calls = {"post": 0, "existing": False}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "pilot.zendesk.com"
        if request.method == "GET":
            return httpx.Response(200, json={"results": [
                {"id": 731, "external_id": "supportpilot:ws:ticket"}
            ] if calls["existing"] else []})
        calls["post"] += 1
        assert request.headers["Idempotency-Key"] == "supportpilot:ws:ticket"
        if calls["post"] == 1:
            raise httpx.ReadTimeout("outcome unknown")
        return httpx.Response(201, json={"ticket": {"id": 731}})

    adapter = ZendeskTicketAdapter("pilot", "agent@example.test", "test-token",
                                   client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        adapter.create_ticket(subject="Pilot", body="Context", external_id="supportpilot:ws:ticket")
    except AmbiguousWrite:
        pass
    else:
        raise AssertionError("A timeout must not be reported as a successful write")
    calls["existing"] = True
    assert adapter.create_ticket(subject="Pilot", body="Context",
                                 external_id="supportpilot:ws:ticket") == "731"
    assert calls["post"] == 1


def test_ticket_sync_keeps_local_ticket_and_reconciles_after_uncertain_write(client, monkeypatch):
    class FlakySupport:
        calls = 0

        def create_ticket(self, *, subject: str, body: str, external_id: str) -> str:
            self.calls += 1
            if self.calls == 1:
                raise AmbiguousWrite("Provider timed out")
            assert "supportpilot:ws_northstar:" in external_id
            return "provider-731"

    adapter = FlakySupport()
    monkeypatch.setattr("supportpilot.tickets.support_for", lambda: adapter)
    login(client, "ns.customer.0001@example.test")
    conversation = client.post("/api/conversations", json={"subject": "Ambiguous ticket test"}).json()
    result = client.post(f"/api/conversations/{conversation['id']}/escalate")
    assert result.status_code == 503
    with SessionLocal() as db:
        ticket = db.scalar(select(Ticket).where(Ticket.conversation_id == conversation["id"]))
        assert ticket and ticket.sync_status == "uncertain"
        ticket_id = ticket.id
    client.post("/api/auth/logout")
    login(client, "operator.ns@example.test")
    synced = client.post(f"/api/tickets/{ticket_id}/sync")
    assert synced.status_code == 200, synced.text
    assert synced.json()["sync_status"] == "complete"
    assert synced.json()["external_ticket_id"] == "provider-731"
    assert client.post(f"/api/tickets/{ticket_id}/sync").status_code == 200
    assert adapter.calls == 2
    with SessionLocal() as db:
        assert db.scalar(select(func.count(ActionLedger.id)).where(
            ActionLedger.action_key == f"ticket:ws_northstar:{ticket_id}")) == 1
