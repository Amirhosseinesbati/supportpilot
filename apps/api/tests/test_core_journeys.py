from __future__ import annotations

import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from supportpilot.api import app
from supportpilot.db import SessionLocal
from supportpilot.domain import assess_return
from supportpilot.graphs import run_chat
from supportpilot.knowledge import activate_version, add_document, process_job, retrieve
from supportpilot.models import (
    ActionLedger,
    Approval,
    Document,
    DocumentVersion,
    IngestionJob,
    ReturnRecord,
    Shipment,
    Ticket,
    Workspace,
    now,
    uid,
)

from .conftest import login


def test_return_policy_is_deterministic_and_workspace_configurable():
    decision = assess_return(delivered_on=date(2026, 8, 26), requested_on=date(2026, 9, 27),
        category="monitor", condition="unopened", ordered_quantity=1,
        already_returned=0, requested_quantity=1, late_delivery_days=12,
        policy={"monitor_days": 21, "late_delivery_grace_days": 45, "late_threshold_days": 7})
    assert decision.eligible and decision.requires_review
    assert decision.code == "late_delivery_exception"
    denied = assess_return(delivered_on=date(2026, 8, 26), requested_on=date(2026, 9, 27),
        category="monitor", condition="unopened", ordered_quantity=1,
        already_returned=0, requested_quantity=1, late_delivery_days=1,
        policy={"monitor_days": 21, "late_delivery_grace_days": 45, "late_threshold_days": 7})
    assert not denied.eligible
    outside_with_unknown_condition = assess_return(
        delivered_on=date(2026, 1, 1), requested_on=date(2026, 9, 27),
        category="accessory", condition="unknown", ordered_quantity=1,
        already_returned=0, requested_quantity=1)
    assert outside_with_unknown_condition.code == "outside_window"


def test_cross_workspace_and_same_workspace_other_customer_are_hidden(client):
    login(client, "ns.customer.0001@example.test")
    assert client.get("/api/orders/ord_hb_00401").status_code == 404
    assert client.get("/api/orders/ord_ns_00002").status_code == 404
    assert client.get("/api/conversations/conv_hb_00401").status_code == 404
    response = client.post("/api/conversations/conv_ns_demo_001/messages",
                           json={"content": "Where is order NS-000002?"})
    assert response.status_code == 200
    assert "verified account" in response.json()["assistant"]["content"]
    assert "NS-000002" not in response.json()["assistant"]["content"]


def test_staff_cannot_read_or_execute_in_another_workspace(client):
    login(client, "admin.ns@example.test")
    assert client.get("/api/conversations/conv_hb_0001").status_code == 404
    assert client.get("/api/orders/ord_hb_00001").status_code == 404
    assert client.get("/api/sources/doc_hb_policy_returns_v2_c1").status_code == 404
    assert all(item["id"] != "doc_hb_policy_returns" for item in
               client.get("/api/documents").json()["items"])
    assert client.post("/api/proposals/proposal_hb_001/review",
                       json={"decision": "approve", "version": "1"}).status_code == 404
    assert client.post("/api/returns/proposals", json={
        "order_id": "ord_hb_00001", "line_id": "line_hb_00001_1", "quantity": 1,
        "condition": "unopened", "reason": "Wrong workspace",
        "conversation_id": "conv_ns_demo_001"}).status_code == 404


def test_admin_onboarding_and_partial_delivery_does_not_allow_return(client):
    login(client, "admin.ns@example.test")
    created_customer = client.post("/api/admin/customers", json={
        "name": "Pilot Buyer", "email": "pilot.buyer@example.test",
        "password": "UniquePilotPass!2026"})
    assert created_customer.status_code == 200, created_customer.text
    customer_id = created_customer.json()["id"]
    assert client.post("/api/admin/customers", json={
        "name": "Pilot Buyer", "email": "pilot.buyer@example.test",
        "password": "UniquePilotPass!2026"}).status_code == 409
    product = client.post("/api/admin/products", json={
        "sku": "PILOT-MONITOR-01", "name": "Pilot monitor", "category": "monitor",
        "price_cents": 34900})
    assert product.status_code == 200, product.text
    product_id = product.json()["id"]
    assert client.patch(f"/api/admin/products/{product_id}",
                        json={"category": "monitor"}).status_code == 200
    assert client.patch(f"/api/admin/products/{product_id}",
                        json={"category": "unclassified"}).status_code == 422
    order = client.post("/api/admin/orders", json={
        "customer_id": customer_id, "number": "NS-PILOT-01",
        "placed_at": "2026-09-18T00:00:00Z", "status": "in_transit",
        "lines": [{"product_id": product_id, "quantity": 1, "unit_price_cents": 34900}],
        "shipments": [
            {"status": "delivered", "delivered_at": "2026-09-22T12:00:00Z"},
            {"status": "in_transit", "shipped_at": "2026-09-23T12:00:00Z"},
        ]})
    assert order.status_code == 200, order.text
    assert order.json()["total_cents"] == 34900
    order_id = order.json()["id"]
    line_id = order.json()["lines"][0]["id"]
    client.post("/api/auth/logout")
    login(client, "ns.customer.0001@example.test")
    assert client.get(f"/api/orders/{order_id}").status_code == 404
    client.post("/api/auth/logout")
    own_login = client.post("/api/auth/login", json={"email": "pilot.buyer@example.test",
        "password": "UniquePilotPass!2026"})
    assert own_login.status_code == 200
    assert client.get(f"/api/orders/{order_id}").status_code == 200
    proposal = client.post("/api/returns/proposals", json={
        "order_id": order_id, "line_id": line_id, "quantity": 1,
        "condition": "unopened", "reason": "Partial shipment still in transit"})
    assert proposal.status_code == 200, proposal.text
    assert proposal.json()["proposal"]["policy_result"]["code"] == "not_delivered"
    assert proposal.json()["proposal"]["return_record_id"] is None
    version = proposal.json()["proposal"]["version"]
    proposal_id = proposal.json()["proposal"]["id"]
    client.post("/api/auth/logout")
    login(client, "admin.ns@example.test")
    assert client.post(f"/api/proposals/{proposal_id}/review",
                       json={"decision": "approve", "version": version}).status_code == 409


def test_escalation_handoff_has_only_verified_order_context(client):
    login(client, "ns.customer.0001@example.test")
    conversation = client.post("/api/conversations", json={"subject": "Late delivery handoff"}).json()
    posted = client.post(f"/api/conversations/{conversation['id']}/messages", json={
        "content": "My order NS-000001 arrived late. Please check the delivery."})
    assert posted.status_code == 200, posted.text
    handoff = client.post(f"/api/conversations/{conversation['id']}/escalate")
    assert handoff.status_code == 200, handoff.text
    assert [item["number"] for item in handoff.json()["order_context"]] == ["NS-000001"]
    assert handoff.json()["order_context"][0]["id"] == "ord_ns_demo_001"

    foreign = client.post("/api/conversations", json={"subject": "Unknown order handoff"}).json()
    posted = client.post(f"/api/conversations/{foreign['id']}/messages", json={
        "content": "Please look up order NS-000002 and escalate."})
    assert posted.status_code == 200, posted.text
    denied_handoff = client.post(f"/api/conversations/{foreign['id']}/escalate")
    assert denied_handoff.status_code == 200, denied_handoff.text
    assert denied_handoff.json()["order_context"] == []


def test_ticket_sync_lease_blocks_active_claim_and_reclaims_stale_claim(client):
    login(client, "ns.customer.0001@example.test")
    conversation = client.post("/api/conversations", json={"subject": "Ticket claim test"}).json()
    ticket = client.post(f"/api/conversations/{conversation['id']}/escalate").json()
    ticket_id = ticket["id"]
    client.post("/api/auth/logout")
    login(client, "operator.ns@example.test")
    with SessionLocal() as db:
        row = db.get(Ticket, ticket_id)
        ledger = db.scalar(select(ActionLedger).where(
            ActionLedger.action_key == f"ticket:ws_northstar:{ticket_id}"))
        created_at = ledger.created_at
        row.external_ticket_id = None
        row.sync_status = "claimed"
        ledger.status = "claimed"
        ledger.lease_until = now() + timedelta(minutes=5)
        db.commit()
    assert client.post(f"/api/tickets/{ticket_id}/sync").status_code == 409
    with SessionLocal() as db:
        ledger = db.scalar(select(ActionLedger).where(
            ActionLedger.action_key == f"ticket:ws_northstar:{ticket_id}"))
        ledger.lease_until = now() - timedelta(minutes=1)
        db.commit()
    recovered = client.post(f"/api/tickets/{ticket_id}/sync")
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["sync_status"] == "complete"
    with SessionLocal() as db:
        ledger = db.scalar(select(ActionLedger).where(
            ActionLedger.action_key == f"ticket:ws_northstar:{ticket_id}"))
        assert ledger.created_at == created_at
        assert ledger.lease_until is None


def test_approval_rechecks_delivery_after_proposal(client):
    login(client, "ns.customer.0001@example.test")
    response = client.post("/api/returns/proposals", json={
        "order_id": "ord_ns_demo_001", "line_id": "line_ns_demo_001",
        "quantity": 1, "condition": "damaged",
        "reason": "Damage review before delivery status changed",
        "conversation_id": "conv_ns_demo_001"})
    assert response.status_code == 200, response.text
    proposal = response.json()["proposal"]
    assert proposal["status"] == "pending_review" and proposal["policy_result"]["eligible"]
    with SessionLocal() as db:
        shipment = db.get(Shipment, "ship_ns_00001")
        shipment.status = "in_transit"
        db.commit()
    try:
        client.post("/api/auth/logout")
        login(client, "operator.ns@example.test")
        refused = client.post(f"/api/proposals/{proposal['id']}/review", json={
            "decision": "approve", "version": proposal["version"]})
        assert refused.status_code == 409, refused.text
        with SessionLocal() as db:
            assert db.scalar(select(func.count(ReturnRecord.id)).where(
                ReturnRecord.proposal_id == proposal["id"])) == 0
    finally:
        with SessionLocal() as db:
            shipment = db.get(Shipment, "ship_ns_00001")
            shipment.status = "delivered"
            db.commit()


def test_admin_can_cancel_and_retry_a_queued_ingestion_job(seeded_database, monkeypatch):
    monkeypatch.setattr("supportpilot.api.claim_next_job", lambda db: None)
    with TestClient(app) as client:
        login(client, "admin.ns@example.test")
        uploaded = client.post("/api/documents", data={"category": "general"}, files={
            "file": ("cancel-test.md", b"# Cancel test\n\nThe queue should stop this job.", "text/markdown")})
        assert uploaded.status_code == 200, uploaded.text
        doc_id = uploaded.json()["document"]["id"]
        job_id = uploaded.json()["job"]["id"]
        cancelled = client.post(f"/api/ingestion-jobs/{job_id}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        assert client.post(f"/api/documents/{doc_id}/publish").status_code == 409
        jobs = client.get("/api/documents").json()["jobs"]
        assert next(item for item in jobs if item["id"] == job_id)["status"] == "cancelled"
        retried = client.post(f"/api/documents/{doc_id}/retry")
        assert retried.status_code == 200, retried.text
        assert retried.json()["job"]["status"] == "pending"
        retry_id = retried.json()["job"]["id"]
        with SessionLocal() as db:
            running = db.get(IngestionJob, retry_id)
            running.status = "running"
            db.commit()
        flagged = client.post(f"/api/ingestion-jobs/{retry_id}/cancel")
        assert flagged.status_code == 200 and flagged.json()["cancel_requested"]
        with SessionLocal() as db:
            process_job(db, db.get(IngestionJob, retry_id))
            assert db.get(IngestionJob, retry_id).status == "cancelled"
            assert db.get(Document, doc_id).status == "draft"


def test_chat_return_review_and_repeated_approval(client):
    login(client, "ns.customer.0001@example.test")
    chat = client.post("/api/conversations/conv_ns_demo_001/messages",
                       json={"content": "My monitor order NS-000001 arrived late. What is the return policy?"})
    assert chat.status_code == 200, chat.text
    assert chat.json()["assistant"]["citations"]
    assert chat.json()["assistant"]["citations"][0]["document_title"] == "Returns and exceptions"
    proposal = client.post("/api/returns/proposals", json={"order_id": "ord_ns_demo_001",
        "line_id": "line_ns_demo_001", "quantity": 1, "condition": "unopened",
        "reason": "Browser journey late monitor return", "conversation_id": "conv_ns_demo_001"})
    assert proposal.status_code == 200, proposal.text
    value = proposal.json()["proposal"]
    assert value["status"] == "pending_review"
    client.post("/api/auth/logout")
    login(client, "operator.ns@example.test")
    first = client.post(f"/api/proposals/{value['id']}/review",
                        json={"decision": "approve", "version": value["version"]})
    second = client.post(f"/api/proposals/{value['id']}/review",
                         json={"decision": "approve", "version": value["version"]})
    assert first.status_code == 200, first.text
    assert second.status_code == 200 and second.json()["idempotent_replay"]
    assert first.json()["proposal"]["return_record_id"] == second.json()["proposal"]["return_record_id"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count(ReturnRecord.id)).where(ReturnRecord.proposal_id == value["id"])) == 1


def test_guest_challenge_is_local_and_one_time(client):
    response = client.post("/api/guest/challenges", json={"workspace_id": "ws_northstar",
        "order_number": "NS-000001", "email": "ns.customer.0001@example.test"})
    assert response.status_code == 200
    body = response.json()
    assert "Synthetic demo" in body["notice"]
    verified = client.post(f"/api/guest/challenges/{body['challenge_id']}/verify",
                           json={"code": body["simulated_code"]})
    assert verified.status_code == 200
    assert verified.json()["order"]["number"] == "NS-000001"
    assert client.post(f"/api/guest/challenges/{body['challenge_id']}/verify",
                       json={"code": body["simulated_code"]}).status_code == 410


def test_unsupported_future_shipping_claim_clarifies_and_streams(client):
    login(client, "ns.customer.0001@example.test")
    response = client.post("/api/conversations/conv_ns_demo_001/messages/stream",
                           json={"content": "Will the unreleased Aster Display 01 ship next month?"})
    assert response.status_code == 200, response.text
    assert "event: answer_chunk" in response.text
    assert "event: final" in response.text
    conversation = client.get("/api/conversations/conv_ns_demo_001").json()
    assistant = conversation["messages"][-1]
    assert assistant["next_action"] == "clarify"
    assert not assistant["citations"]
    assert "published release or shipment date" in assistant["content"]


def test_workspace_authority_priority_controls_conflicting_sources(seeded_database):
    with SessionLocal() as db:
        doc, job = add_document(db, workspace_id="ws_northstar", filename="Returns overview FAQ.md",
                                raw=(b"# Returns overview FAQ\n\nMost unopened items can be returned within "
                                     b"30 days. This FAQ omits the monitor exception; use the official "
                                     b"Returns and exceptions policy for monitor deadlines."),
                                category="returns")
        process_job(db, job)
        version = db.get(DocumentVersion, job.document_version_id)
        assert version and doc.authority == "faq"
        activate_version(db, doc, version)
        workspace = db.get(Workspace, "ws_northstar")
        original = list(workspace.policy_priority)
        workspace.policy_priority = ["faq", "official_policy", "product_manual"]
        db.commit()
    try:
        answer = run_chat(workspace_id="ws_northstar", conversation_id="authority-test",
                          customer_id="", message_id=uid(),
                          question="The returns FAQ and monitor policy give different windows. Compare both sources.")
        assert answer["citations"][0]["document_title"] == "Returns overview FAQ"
        assert "configured priority" in answer["answer"]
    finally:
        with SessionLocal() as db:
            workspace = db.get(Workspace, "ws_northstar")
            workspace.policy_priority = original
            created = db.get(Document, doc.id)
            created.deleted_at = now()
            db.commit()


def test_restarted_concurrent_approval_has_one_record(seeded_database):
    # The child process creates the paused checkpoint, exits, and this process resumes it.
    subprocess.run([sys.executable, "-c",
        "from supportpilot.review_graph import start_review; "
        "start_review(workspace_id='ws_harbor', proposal_id='proposal_hb_001', version='1')"],
        check=True, timeout=30)
    barrier = Barrier(2)

    def approve() -> int:
        with TestClient(app) as client:
            login(client, "operator.hb@example.test")
            barrier.wait()
            response = client.post("/api/proposals/proposal_hb_001/review",
                                   json={"decision": "approve", "version": "1"})
            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: approve(), range(2)))
    assert set(statuses) <= {200, 409}
    assert 200 in statuses
    with SessionLocal() as db:
        assert db.scalar(select(func.count(ReturnRecord.id)).where(
            ReturnRecord.proposal_id == "proposal_hb_001")) == 1
        assert db.scalar(select(func.count(Approval.id)).where(
            Approval.proposal_id == "proposal_hb_001")) == 1
        assert db.scalar(select(func.count(ActionLedger.id)).where(
            ActionLedger.action_key == "return:ws_harbor:proposal_hb_001")) == 1


def test_document_replace_and_delete_invalidate_retrieval(client):
    login(client, "admin.ns@example.test")
    created = client.post("/api/documents", data={"category": "returns"},
        files={"file": ("proof.md", b"# Distinct pilot policy\n\nBlueberry displays have an 18-day inspection period.", "text/markdown")})
    assert created.status_code == 200, created.text
    doc_id = created.json()["document"]["id"]

    def wait_job():
        for _ in range(60):
            jobs = client.get("/api/documents").json()["jobs"]
            job = next(job for job in jobs if job["document_id"] == doc_id)
            if job["status"] in {"completed", "failed"}:
                return job
            time.sleep(0.1)
        raise AssertionError("Job did not complete")

    assert wait_job()["status"] == "completed"
    assert client.post(f"/api/documents/{doc_id}/publish").status_code == 200
    with SessionLocal() as db:
        assert any("Blueberry" in p.passage for p in retrieve(db, workspace_id="ws_northstar",
                   question="Blueberry 18-day inspection period"))
    replaced = client.post(f"/api/documents/{doc_id}/versions",
        files={"file": ("proof.md", b"# Distinct pilot policy\n\nCranberry displays have a 12-day inspection period.", "text/markdown")})
    assert replaced.status_code == 200, replaced.text
    assert wait_job()["status"] == "completed"
    with SessionLocal() as db:
        passages = retrieve(db, workspace_id="ws_northstar", question="Blueberry 18-day inspection period")
        assert all("Blueberry" not in p.passage for p in passages)
        assert any("Cranberry" in p.passage for p in retrieve(db, workspace_id="ws_northstar",
                   question="Cranberry 12-day inspection period"))
    assert client.delete(f"/api/documents/{doc_id}").status_code == 200
    with SessionLocal() as db:
        assert all("Cranberry" not in p.passage for p in retrieve(db, workspace_id="ws_northstar",
                   question="Cranberry 12-day inspection period"))
