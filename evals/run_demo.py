"""Run every evaluation input against the actual local DEMO graph.

This records raw answers and machine-extracted fields. It does not assert that
those fields or cited passages are semantically correct; human review remains
necessary for the release targets.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from sqlalchemy import select  # noqa: E402

from supportpilot.config import settings  # noqa: E402
from supportpilot.db import SessionLocal  # noqa: E402
from supportpilot.graphs import run_chat  # noqa: E402
from supportpilot.models import Chunk, DocumentVersion  # noqa: E402


def extract_claims(answer: str, result: dict) -> dict[str, object]:
    claims: dict[str, object] = {}
    for label, value in re.findall(r"(?:^|\n)\s*[-*]\s*([^:\n]{2,35}):\s*([^\n]+)", answer):
        key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        claims[key] = value.strip().rstrip(".")
    match = re.search(r"Monitors have a (\d+)[- ]day window", answer, re.I)
    if match:
        claims["monitor_return_window_days"] = int(match.group(1))
    match = re.search(r"standard return within (\d+) calendar days", answer, re.I)
    if match:
        claims["standard_return_window_days"] = int(match.group(1))
    match = re.search(r"delivered scan is (\d+) or more calendar days (?:later than|after)", answer, re.I)
    if match:
        claims["late_delivery_threshold_days"] = int(match.group(1))
    if "24 months" in answer:
        claims["major_warranty_months"] = 24
    if "12 months" in answer:
        claims["minor_warranty_months"] = 12
    if any(phrase in answer.lower() for phrase in (
        "no money movement", "no refund", "does not issue refunds", "never moves funds")):
        claims["pilot_can_issue_refunds"] = False
    if "order number" in answer.lower() and any(phrase in answer.lower() for phrase in (
        "not proof", "does not authenticate", "not authentication", "never changes identity",
        "never authorizes a lookup")):
        claims["order_number_is_authentication"] = False
    if any(phrase in answer.lower() for phrase in (
        "displayport alternate mode", "displayport alt mode", "dp alt mode")):
        claims["dock_video_requires_dp_alt_mode"] = True
    if result.get("policy_result"):
        claims["policy_result"] = result["policy_result"]
        claims["policy_reason"] = result.get("policy_reason")
    order = result.get("order")
    if order:
        claims["order_status"] = order["status"]
        if order.get("shipments"):
            claims["shipment_status"] = order["shipments"][0]["status"]
    return claims


def main() -> None:
    if settings.connected:
        raise SystemExit("Use DEMO mode for this deterministic fixture run")
    cases = [json.loads(line) for line in (ROOT / "evals" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line]
    output = ROOT / "evals" / "predictions.demo.jsonl"
    run_id = uuid4().hex[:12]
    rows = []
    for index, case in enumerate(cases, start=1):
        source = case["input"]
        actor = source.get("actor") or {}
        started = perf_counter()
        try:
            result = run_chat(workspace_id=source["workspace_id"],
                conversation_id=f"eval-{case['id']}",
                customer_id=actor.get("customer_id", ""),
                message_id=f"eval-{run_id}-{case['id']}", question=source["message"],
                as_of=source.get("as_of"))
            elapsed = (perf_counter() - started) * 1000
            chunk_ids = [citation["chunk_id"] for citation in result.get("citations", [])]
            with SessionLocal() as db:
                citations = [db.scalar(select(DocumentVersion.id).join(
                    Chunk, Chunk.document_version_id == DocumentVersion.id).where(Chunk.id == chunk_id))
                    for chunk_id in chunk_ids]
            next_action = result.get("next_action", "none")
            if result.get("policy_result") == "ineligible":
                next_action = "explain_ineligible"
            elif result.get("policy_result") in {"eligible", "review_required", "exception_review"}:
                next_action = "draft_action"
            row = {"id": case["id"], "answer": result.get("answer", ""),
                   "next_action": "answer" if next_action == "none" else next_action,
                   "claims": extract_claims(result.get("answer", ""), result),
                   "citations": [citation for citation in citations if citation],
                   "latency_ms": round(elapsed, 2), "cost_usd": 0.0,
                   "tool_success": any(event.get("result") == "found" for event in result.get("tool_events", []))
                   if case["category"] == "tool_action" else None,
                   "mode": "DEMO", "model": "deterministic_fixture"}
        except Exception as error:
            row = {"id": case["id"], "answer": "", "next_action": "error",
                   "claims": {}, "citations": [], "latency_ms": round((perf_counter() - started) * 1000, 2),
                   "error": f"{type(error).__name__}: {error}"}
        rows.append(row)
        if index % 40 == 0:
            print(f"{index}/{len(cases)} cases")
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"Wrote {output} ({sum('error' in row for row in rows)} errors)")


if __name__ == "__main__":
    main()
