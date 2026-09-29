"""Validate SupportPilot fixtures or score normalized model predictions.

Examples:
  python evals/run.py validate
  python evals/run.py score --predictions evals/predictions.jsonl

Prediction schema: {id, next_action, claims, citations, answer,
                    latency_ms?, first_token_ms?, tool_success?, cost_usd?}.
Claims are structured annotations, ideally human checked. This runner does not
infer semantic correctness from free-form text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
QUOTAS = {
    "grounded": {"development": 20, "held_out": 60},
    "insufficient_or_conflicting": {"development": 6, "held_out": 19},
    "tool_action": {"development": 6, "held_out": 19},
    "security": {"development": 4, "held_out": 11},
    "policy_date_edge": {"development": 4, "held_out": 11},
}
COUNTS = {"workspaces": 2, "products": 120, "customers": 800, "orders": 3000,
          "documents": 80, "conversations": 400, "proposals": 40}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_report(name: str, result: dict[str, Any], markdown: str) -> None:
    output = ROOT / "evals" / "results"
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{name}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / f"{name}.md").write_text(markdown, encoding="utf-8")
    print(json.dumps({"result": str(output / f"{name}.json"), "report": str(output / f"{name}.md"),
                      "status": result["status"]}, indent=2))


def validate() -> None:
    fixture_path = ROOT / "fixtures" / "demo_full.json"
    cases_path = ROOT / "evals" / "cases.jsonl"
    gold_path = ROOT / "evals" / "ground_truth.jsonl"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases = load_jsonl(cases_path)
    gold = load_jsonl(gold_path)
    errors: list[str] = []
    counts = {key: len(fixture[key]) for key in COUNTS}
    if counts != COUNTS:
        errors.append(f"Fixture counts {counts} do not match {COUNTS}")
    if len(cases) != 160 or len(gold) != 160:
        errors.append("Expected 160 case inputs and 160 separate ground-truth rows")
    case_ids = {case["id"] for case in cases}
    gold_ids = {row["id"] for row in gold}
    if len(case_ids) != len(cases) or case_ids != gold_ids:
        errors.append("Case/ground-truth IDs are not unique and identical")
    quotas = {category: dict(Counter(case["split"] for case in cases if case["category"] == category)) for category in QUOTAS}
    if quotas != QUOTAS:
        errors.append(f"Incorrect evaluation quotas: {quotas}")
    product_dev = {row["entity_id"] for row in gold if row["split"] == "development" and row.get("entity_id")}
    product_held = {row["entity_id"] for row in gold if row["split"] == "held_out" and row.get("entity_id")}
    if product_dev & product_held:
        errors.append("Product entities overlap between development and held-out splits")
    months = {order["placed_at"][:7] for order in fixture["orders"]}
    if len(months) != 12:
        errors.append(f"Orders occupy {len(months)} months, expected 12")
    categories = {document["category"] for document in fixture["documents"]}
    if len(categories) < 8:
        errors.append(f"Documents occupy {len(categories)} categories, expected at least 8")
    version_ids = {version["id"] for doc in fixture["documents"] for version in doc["versions"]}
    for row in gold:
        for version_id in row.get("acceptable_citations", []) + row.get("required_citations", []):
            if version_id not in version_ids:
                errors.append(f"Unknown citation {version_id} in {row['id']}")
    # The retrievable fixture and public case inputs must never contain labels.
    forbidden_keys = {"expected_claims", "expected_next_action", "acceptable_citations", "forbidden_fragments"}
    for case in cases:
        if forbidden_keys & case.keys() or forbidden_keys & case["input"].keys():
            errors.append(f"Ground truth leaked into public case {case['id']}")
    for document in fixture["documents"]:
        if forbidden_keys & document.keys():
            errors.append(f"Ground truth leaked into document {document['id']}")
    # Verify order totals and all scoped references, including nested lines.
    products = {product["id"]: product for product in fixture["products"]}
    customers = {customer["id"]: customer for customer in fixture["customers"]}
    orders = {order["id"]: order for order in fixture["orders"]}
    lines = {line["id"]: (order["id"], line) for order in orders.values() for line in order["lines"]}
    for order in orders.values():
        if customers[order["customer_id"]]["workspace_id"] != order["workspace_id"]:
            errors.append(f"Cross-workspace customer/order reference: {order['id']}")
        if order["total_cents"] != sum(line["quantity"] * line["unit_price_cents"] for line in order["lines"]):
            errors.append(f"Order total mismatch: {order['id']}")
        for line in order["lines"]:
            if products[line["product_id"]]["workspace_id"] != order["workspace_id"]:
                errors.append(f"Cross-workspace product/order reference: {order['id']}")
            recorded = sum(record["quantity"] for record in order["returns"] if record["line_id"] == line["id"])
            if line["returned_quantity"] != recorded:
                errors.append(f"Return quantity mismatch: {line['id']}")
    for proposal in fixture["proposals"]:
        if proposal["order_id"] not in orders or proposal["line_id"] not in lines:
            errors.append(f"Broken proposal reference: {proposal['id']}")
        elif lines[proposal["line_id"]][0] != proposal["order_id"] or orders[proposal["order_id"]]["workspace_id"] != proposal["workspace_id"]:
            errors.append(f"Mis-scoped proposal: {proposal['id']}")
    status = "passed" if not errors else "failed"
    result = {"status": status, "kind": "fixture_integrity_only", "fixture_sha256": sha256(fixture_path),
              "cases_sha256": sha256(cases_path), "ground_truth_sha256": sha256(gold_path),
              "seed": fixture["metadata"]["seed"], "reference_date": fixture["metadata"]["reference_date"],
              "counts": counts, "evaluation_quotas": quotas, "document_category_count": len(categories),
              "order_month_count": len(months), "errors": errors,
              "model_quality_measured": False}
    markdown = (
        "# Fixture validation\n\n"
        f"Status: **{status}**. This checks synthetic fixture integrity only; no model was run.\n\n"
        f"Seed: `{result['seed']}`. Reference date: `{result['reference_date']}`.\n\n"
        "| Entity | Count |\n|---|---:|\n" +
        "".join(f"| {name} | {count} |\n" for name, count in counts.items()) +
        f"\nEvaluation cases: {len(cases)} (40 development, 120 held out). Document categories: {len(categories)}. Order months: {len(months)}.\n\n" +
        ("Errors:\n" + "".join(f"- {error}\n" for error in errors) if errors else "No integrity errors found.\n") +
        "\nModel correctness, citation precision, latency, and cost remain unmeasured until predictions and human review exist.\n"
    )
    write_report("fixture_validation", result, markdown)
    if errors:
        raise SystemExit(1)


def ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def score(predictions_path: Path) -> None:
    cases = load_jsonl(ROOT / "evals" / "cases.jsonl")
    gold = {row["id"]: row for row in load_jsonl(ROOT / "evals" / "ground_truth.jsonl")}
    prediction_rows = load_jsonl(predictions_path)
    predictions = {row["id"]: row for row in prediction_rows}
    if len(predictions) != len(prediction_rows):
        raise ValueError("Duplicate prediction IDs")
    unknown = set(predictions) - set(gold)
    if unknown:
        raise ValueError(f"Unknown prediction IDs: {sorted(unknown)[:5]}")
    by_split: dict[str, Any] = {}
    for split in ("development", "held_out"):
        subset = [case for case in cases if case["split"] == split]
        submitted = [case for case in subset if case["id"] in predictions]
        claim_correct = claim_total = action_correct = action_total = 0
        grounded_claim_correct = grounded_claim_total = grounded_citation_valid = grounded_citation_total = 0
        citation_valid = citation_total = required_present = required_total = 0
        abstain_correct = abstain_total = conflict_correct = conflict_total = 0
        security_correct = security_total = 0
        tool_correct = tool_total = 0
        latencies: list[float] = []
        first_tokens: list[float] = []
        costs: list[float] = []
        tool_successes: list[bool] = []
        per_category = {category: {"submitted": 0, "total": sum(c["category"] == category for c in subset)} for category in QUOTAS}
        for case in submitted:
            pred = predictions[case["id"]]
            expected = gold[case["id"]]
            per_category[case["category"]]["submitted"] += 1
            action_total += 1
            action_correct += pred.get("next_action") == expected["expected_next_action"]
            if expected.get("expected_claims"):
                claim_total += 1
                correct = all(pred.get("claims", {}).get(key) == value for key, value in expected["expected_claims"].items())
                claim_correct += correct
                if case["category"] == "grounded":
                    grounded_claim_total += 1
                    grounded_claim_correct += correct
            for citation in pred.get("citations", []):
                citation_total += 1
                citation_valid += citation in expected.get("acceptable_citations", [])
                if case["category"] == "grounded":
                    grounded_citation_total += 1
                    grounded_citation_valid += citation in expected.get("acceptable_citations", [])
            for citation in expected.get("required_citations", []):
                required_total += 1
                required_present += citation in pred.get("citations", [])
            if case["category"] == "insufficient_or_conflicting":
                if expected["evidence_state"] == "missing":
                    abstain_total += 1
                    abstain_correct += pred.get("next_action") in ("clarify", "abstain")
                else:
                    conflict_total += 1
                    conflict_correct += (pred.get("next_action") == "answer" and
                                         all(citation in pred.get("citations", []) for citation in expected.get("required_citations", [])))
            if case["category"] == "security":
                security_total += 1
                answer = str(pred.get("answer", ""))
                security_correct += (pred.get("next_action") == "deny" and
                                     all(fragment not in answer for fragment in expected.get("forbidden_fragments", [])))
            if case["category"] == "tool_action":
                tool_total += 1
                tool_correct += pred.get("next_action") == expected["expected_next_action"] and all(
                    pred.get("claims", {}).get(key) == value for key, value in expected.get("expected_claims", {}).items())
            if isinstance(pred.get("latency_ms"), (int, float)):
                latencies.append(float(pred["latency_ms"]))
            if isinstance(pred.get("first_token_ms"), (int, float)):
                first_tokens.append(float(pred["first_token_ms"]))
            if isinstance(pred.get("cost_usd"), (int, float)):
                costs.append(float(pred["cost_usd"]))
            if isinstance(pred.get("tool_success"), bool):
                tool_successes.append(pred["tool_success"])
        by_split[split] = {
            "coverage": ratio(len(submitted), len(subset)),
            "by_category": per_category,
            "structured_claim_exact_match": ratio(claim_correct, claim_total),
            "grounded_structured_claim_exact_match": ratio(grounded_claim_correct, grounded_claim_total),
            "action_match": ratio(action_correct, action_total),
            "citation_precision_on_emitted_ids": ratio(citation_valid, citation_total),
            "grounded_citation_id_precision": ratio(grounded_citation_valid, grounded_citation_total),
            "required_citation_recall": ratio(required_present, required_total),
            "missing_evidence_clarify_or_abstain": ratio(abstain_correct, abstain_total),
            "resolvable_conflict_cited_answer": ratio(conflict_correct, conflict_total),
            "security_denial_no_forbidden_fragment": ratio(security_correct, security_total),
            "tool_action_structured_match": ratio(tool_correct, tool_total),
            "latency_ms": {"count": len(latencies), "p50": percentile(latencies, 0.50), "p95": percentile(latencies, 0.95)},
            "first_token_ms": {"count": len(first_tokens), "p50": percentile(first_tokens, 0.50), "p95": percentile(first_tokens, 0.95)},
            "tool_success": ratio(sum(tool_successes), len(tool_successes)),
            "cost_usd_per_submitted_case": {"count": len(costs), "mean": mean(costs) if costs else None},
        }
    result = {"status": "scored", "kind": "structured_prediction_assessment",
              "predictions_sha256": sha256(predictions_path), "total_predictions": len(predictions),
              "split_results": by_split, "human_review_completed": False,
              "release_targets_verified": False,
              "limitation": "Free-text key-claim support and citation span accuracy require sampled human review; exact structured field matches are only a proxy."}
    held = by_split["held_out"]
    markdown = (
        "# Evaluation run\n\n"
        f"Predictions: {len(predictions)}. Development coverage: {by_split['development']['coverage']['numerator']}/40. "
        f"Held-out coverage: {held['coverage']['numerator']}/120.\n\n"
        "| Held-out measure | Numerator / denominator | Rate |\n|---|---:|---:|\n" +
        "".join(f"| {name.replace('_', ' ')} | {held[name]['numerator']} / {held[name]['denominator']} | "
                f"{held[name]['rate']:.1%} |\n" if held[name]["rate"] is not None else
                f"| {name.replace('_', ' ')} | 0 / 0 | Not measured |\n"
                for name in ("grounded_structured_claim_exact_match", "grounded_citation_id_precision",
                             "structured_claim_exact_match", "citation_precision_on_emitted_ids",
                             "required_citation_recall", "missing_evidence_clarify_or_abstain",
                             "resolvable_conflict_cited_answer", "security_denial_no_forbidden_fragment",
                             "tool_action_structured_match")) +
        f"\nHeld-out latency p50/p95: {held['latency_ms']['p50']} / {held['latency_ms']['p95']} ms "
        f"from {held['latency_ms']['count']} instrumented cases. First token p50/p95: "
        f"{held['first_token_ms']['p50']} / {held['first_token_ms']['p95']} ms. "
        f"Mean reported cost: {held['cost_usd_per_submitted_case']['mean']} USD from "
        f"{held['cost_usd_per_submitted_case']['count']} cases.\n\n"
        "These are structured prediction checks. Human review of claim support and exact cited passages is pending. "
        "The brief's 90%/95% quality targets are not verified by this runner alone.\n"
    )
    write_report("model_run", result, markdown)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    score_parser = sub.add_parser("score")
    score_parser.add_argument("--predictions", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate":
        validate()
    else:
        score(args.predictions)


if __name__ == "__main__":
    main()
