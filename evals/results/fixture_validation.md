# Fixture validation

Status: **passed**. This checks synthetic fixture integrity only; no model was run.

Seed: `240917`. Reference date: `2026-09-27`.

| Entity | Count |
|---|---:|
| workspaces | 2 |
| products | 120 |
| customers | 800 |
| orders | 3000 |
| documents | 80 |
| conversations | 400 |
| proposals | 40 |

Evaluation cases: 160 (40 development, 120 held out). Document categories: 10. Order months: 12.

No integrity errors found.

Model correctness, citation precision, latency, and cost remain unmeasured until predictions and human review exist.
