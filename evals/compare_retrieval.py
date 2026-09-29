"""Measure simple lexical retrieval against the configured hybrid implementation.

Run from apps/api after seeding the full fixture. PostgreSQL results require a
running PostgreSQL/pgvector database; SQLite results use the deterministic
local approximation and are reported as such.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path
from statistics import median
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from supportpilot.db import SessionLocal, engine  # noqa: E402
from supportpilot.knowledge import retrieve  # noqa: E402


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def main() -> None:
    cases = {row["id"]: row for row in (json.loads(line) for line in
             (ROOT / "evals" / "cases.jsonl").read_text(encoding="utf-8").splitlines())
             if row["category"] == "grounded"}
    gold = {row["id"]: row for row in (json.loads(line) for line in
            (ROOT / "evals" / "ground_truth.jsonl").read_text(encoding="utf-8").splitlines())
            if row["category"] == "grounded"}
    if len(cases) != 80 or set(cases) != set(gold):
        raise RuntimeError("Expected 80 aligned grounded cases")
    results = {}
    for strategy in ("baseline", "hybrid"):
        top1 = top6 = 0
        durations = []
        with SessionLocal() as db:
            for case_id, case in cases.items():
                source = case["input"]
                as_of = datetime.combine(date.fromisoformat(source["as_of"]), time(12), tzinfo=UTC)
                started = perf_counter()
                passages = retrieve(db, workspace_id=source["workspace_id"],
                                    question=source["message"], as_of=as_of,
                                    limit=6, strategy=strategy)
                durations.append((perf_counter() - started) * 1000)
                accepted = gold[case_id]["acceptable_citations"]
                matched = [any(p.chunk_id.startswith(version_id + "_c") for version_id in accepted)
                           for p in passages]
                top1 += bool(matched and matched[0])
                top6 += any(matched)
        results[strategy] = {
            "top1": {"numerator": top1, "denominator": len(cases), "rate": top1 / len(cases)},
            "top6": {"numerator": top6, "denominator": len(cases), "rate": top6 / len(cases)},
            "latency_ms": {"median": median(durations), "p95": percentile(durations, 0.95)},
        }
    report = {
        "database_dialect": engine.dialect.name,
        "retrieval_implementation": ("PostgreSQL full-text plus pgvector" if engine.dialect.name == "postgresql"
                                     else "SQLite lexical plus deterministic local vector approximation"),
        "grounded_cases": len(cases), "results": results,
        "postgresql_hybrid_verified": engine.dialect.name == "postgresql",
        "note": "Source-version hit rates measure retrieval, not answer support or citation precision.",
    }
    output = ROOT / "evals" / "results"
    output.mkdir(exist_ok=True)
    (output / "retrieval_comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown = (f"# Retrieval comparison\n\nDatabase: {report['retrieval_implementation']}. "
                f"80 grounded questions.\n\n"
                "| Strategy | Source in top 1 | Source in top 6 | Median / p95 ms |\n"
                "|---|---:|---:|---:|\n")
    for strategy, values in results.items():
        markdown += (f"| {strategy} | {values['top1']['numerator']}/80 | "
                     f"{values['top6']['numerator']}/80 | "
                     f"{values['latency_ms']['median']:.2f} / {values['latency_ms']['p95']:.2f} |\n")
    if engine.dialect.name != "postgresql":
        markdown += "\nPostgreSQL full-text plus pgvector performance remains unverified until a database is available.\n"
    (output / "retrieval_comparison.md").write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
