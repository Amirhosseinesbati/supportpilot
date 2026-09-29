# Evaluation protocol and current results

The evaluation set contains **160 conversations** generated from structured scenario data, not from a model under test. It is split into 40 development cases and 120 held-out cases. Case inputs are in `evals/cases.jsonl`; answers and expected decisions are in `evals/ground_truth.jsonl`. The ground-truth file must never enter retrieval, a runtime prompt, or the customer-facing build.

| Category | Development | Held out | Total |
|---|---:|---:|---:|
| Grounded questions | 20 | 60 | 80 |
| Missing or conflicting evidence | 6 | 19 | 25 |
| Tool and action cases | 6 | 19 | 25 |
| Cross-workspace or identity attacks | 4 | 11 | 15 |
| Policy-date and return-window edges | 4 | 11 | 15 |
| **Total** | **40** | **120** | **160** |

The grounded product cases use disjoint product/manual entities across splits. The limited policy documents are shared, but held-out prompts vary phrasing and historical effective dates. The case-input file includes the authorized actor and workspace for tool cases. The label file identifies the expected action, structured key claims, acceptable source-version IDs, and disclosures that must be absent. Labels are derived from order data and explicit policy rules.

## Commands

```powershell
python scripts/generate_demo.py --seed 240917 --reference-date 2026-09-27
python scripts/generate_evals.py
python evals/run.py validate
python evals/run.py score --predictions evals/predictions.jsonl
```

For the local fixture graph run, first seed the DEMO database, then run `uv run python ../../evals/run_demo.py` and `uv run python ../../evals/compare_retrieval.py` from `apps/api`; score `evals/predictions.demo.jsonl` from the project root. `run_demo.py` invokes the application graph for every case, records raw answers and extracted fields, and sets `mode=DEMO` and `model=deterministic_fixture`. It does not call a paid model provider. Keep the generated labels separate from that runtime.

`validate` writes `evals/results/fixture_validation.json` and `.md`. It checks counts, references, order totals, returns, source-version IDs, split quotas, and basic leakage. The current generated fixture **passed** this integrity check on 2026-09-27. That result is not a model evaluation.

`score` expects one JSON line per attempted case:

```json
{"id":"eval_grounded_001","next_action":"answer","claims":{"size_in":"27"},"citations":["doc_ns_manual_ns_mon_001_v1"],"answer":"The listed display size is 27 inches.","latency_ms":1234,"first_token_ms":430,"tool_success":true,"cost_usd":0.0021}
```

The example shows the format only; its values are **not a measured run**. `claims` are normalized annotations from the application or a human reviewer, not a conclusion inferred by this runner from free text. The scorer produces per-split numerators, denominators, and rates for structured claims, actions, citation ID precision and required-citation recall, missing-evidence clarification, conflict handling, security denials, and tool cases. It reports p50/p95 response and first-token latency, tool success, and mean reported cost only when the prediction records supply those fields. The output is `evals/results/model_run.json` and `.md`.

## Quality gates and human review

The brief targets at least **90% supported key-claim correctness** and **95% citation precision** on held-out grounded questions, plus **90% appropriate clarification or abstention** on insufficient-evidence cases. Structured claim equality and citation-version ID membership are useful automated checks but cannot prove that the free-text answer is supported by the exact cited passage. A model may cite the right document and still misstate a claim.

`evals/human_review_sample.jsonl` reserves 40 held-out cases for manual review: 20 grounded, 8 missing/conflicting, 6 tool/action, 3 security, and 3 policy-date. It currently contains only `pending` review rows. For every grounded sampled answer, a reviewer should mark each key claim as supported or unsupported against the displayed passage, count valid cited passages among all cited passages, and record a short reason. Review all failures and a random sample of passes, then report both sample and full-set counts. A second reviewer should adjudicate disputed or ambiguous labels before release claims are made.

Additional required gates are end-to-end upload → answer → return proposal → review → recorded action; workspace and customer ownership denial; one return under concurrent repeat approval and restart; and deletion/replacement removing obsolete retrieval results after indexing. `fixtures/provider_failures.json` supplies malformed commerce output, missing scope, a model rate limit, an ambiguous ticket write, and an unsupported citation for adapter/error tests. These fixtures exercise handling; they do not verify Shopify, Zendesk, or any live model.

## Current measured state — 2026-09-27

The final recorded DEMO proxy run submitted **160/160 predictions with 0 execution errors** after the prompt-diversity update. These are actual local graph responses over the synthetic fixture. The runner compares structured fields and citation version IDs; it does not judge whether each sentence is supported by the exact cited passage. `evals/results/model_run.json` and `.md` contain the full machine-readable and readable reports.

| Held-out proxy measure | Result |
|---|---:|
| Coverage | 120/120 |
| Grounded structured claim exact match | 60/60 (100%) |
| Grounded citation version-ID precision | 60/60 (100%) |
| Structured claim exact match across categories | 90/97 (92.8%) |
| Precision across all emitted citation version IDs | 89/104 (85.6%) |
| Required citation recall | 20/20 (100%) |
| Missing-evidence clarification or abstention | 12/12 (100%) |
| Resolvable conflicts answered with required citations | 7/7 (100%) |
| Security denial without forbidden fragment | 11/11 (100%) |
| Tool/action structured match | 19/19 (100%) |
| Local DEMO graph response latency | p50 73.31 ms; p95 87.4945 ms; 120 held-out cases |

The brief's 95% citation-precision target applies to **held-out grounded questions**. Their version-ID proxy is 60/60, but it cannot establish whether the exact cited passages support the answer. Across all evaluation categories, emitted citation version-ID precision is 89/104 (85.6%); this broader measure is a useful warning, not the denominator of the brief's target. The 40 reserved human-review rows remain `pending`; supported free-text key-claim correctness and passage-level grounded citation precision have not been measured. The DEMO fixture records $0 external provider cost because it makes no paid model calls. First-token model latency has no observations, and these local timings do not represent connected-model or browser latency. The report sets `release_targets_verified=false`.

## Retrieval comparison

`evals/compare_retrieval.py` measured the 80 grounded questions against the full SQLite DEMO fixture. Here, baseline means lexical retrieval and hybrid means lexical scoring plus the deterministic local vector approximation and authority/category scoring. A match means an acceptable source version appeared in the specified result positions; it does not prove the final answer used the right passage.

| SQLite strategy | Acceptable source at rank 1 | Within first 6 | Retrieval median / p95 |
|---|---:|---:|---:|
| Lexical baseline | 69/80 | 77/80 | 10.93 / 11.52 ms |
| Local hybrid | 80/80 | 80/80 | 12.08 / 12.83 ms |

The detailed output is in `evals/results/retrieval_comparison.json` and `.md`. This comparison does not measure PostgreSQL full-text plus pgvector; that backend awaits a running database. It also does not substitute for human citation-span review.

| Check | Result |
|---|---|
| Synthetic fixture counts and referential integrity | Passed; see `evals/results/fixture_validation.json` |
| Evaluation split and source-ID validity | Passed; 40 development / 120 held out |
| DEMO graph structured prediction assessment | Recorded; see `evals/results/model_run.json` and limits above |
| SQLite baseline versus hybrid retrieval | 80 grounded cases measured; local hybrid 80/80 top 1 versus baseline 69/80 |
| Connected-model quality and human passage review | Not run |
| Browser workflow and SQLite concurrency gates | Browser journeys reported passed; API concurrency test passed; see [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) |
| Live connector behavior | Pending credentials and bounded smoke tests |
| DEMO graph latency/tool success | Recorded in model run; first-token and connected-model cost unmeasured |

Synthetic evaluation cannot establish real-customer accuracy. A release remains incomplete if the held-out or manual gates are unmet; do not silently lower thresholds or replace missing measurements with fixture scores.
