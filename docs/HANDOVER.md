# Handover — SupportPilot local pilot

**As of:** 2026-09-27. **Repository revision:** run `git rev-parse HEAD` in the project root to identify the checked-out commit; the final delivery response records the committed hash. This is an independent portfolio build using a synthetic demo dataset, not a customer deployment.

## Launch

Prerequisites: Python 3.12, `uv`, Node.js 24, and pnpm 11.19.0. From the project root, use a platform launch script:

```powershell
Set-Location '/path/to/supportpilot'
pwsh -File scripts/demo.ps1 -Size full
```

```bash
cd /path/to/supportpilot
bash scripts/demo.sh full
```

Open `http://localhost:5173`; the API health endpoint is `http://localhost:8000/api/health`. The scripts install from lockfiles, generate a missing fixture, migrate and seed the isolated DEMO database on first launch, then start API and web services. They preserve an existing database unless reset is explicit. Windows `pwsh -NoProfile -File scripts/demo.ps1 -Size full -PrepareOnly` exited 0. A timed full launch on ports 18080/15173 returned healthy direct API, web page, and web API proxy responses; it exited 0 and left no listeners on those ports. Bash syntax passed in Git Bash; runtime on a POSIX host remains untested. Manual fallback commands are in [OPERATIONS.md](OPERATIONS.md).

## Demo credentials

All accounts use the synthetic fixture password `DemoPass!2026`. The importer hashes it before storage. Never use this password or these accounts with a real deployment.

| Role | Email | Purpose |
|---|---|---|
| Northstar admin | `admin.ns@example.test` | Knowledge upload/publish |
| Northstar operator | `operator.ns@example.test` | Review proposals and reply to tickets |
| Northstar viewer | `viewer.ns@example.test` | Read-only operations |
| Northstar customer | `ns.customer.0001@example.test` | Hero order and widget |
| Harbor operator | `operator.hb@example.test` | Isolation check |
| Harbor customer | `hb.customer.0001@example.test` | Second-workspace journey |

The hero IDs are `cust_ns_demo_001`, `ord_ns_demo_001`, `line_ns_demo_001`, `conv_ns_demo_001`, and `proposal_ns_demo_001`. The seeded proposal starts pending review. To demonstrate a fresh approval twice, reset only the DEMO fixture first or create a new proposal with a different reason, then use its returned version.

## Current implementation and evidence

| Capability | Implemented in source | Verified here | Next gate |
|---|---|---|---|
| Deterministic full synthetic data and 160 evaluation cases | Yes | Exact counts/integrity passed; 160/160 DEMO graph predictions with 0 errors | Human passage review and connected-model run |
| Local auth, scoped conversations/orders, return policy, proposal review, local ledger | Yes | `pytest -q`: 23 passed, including a paused checkpoint created in a child process then two concurrent approvals after restart, staff/customer scope denial, return replay, and authority priority | PostgreSQL concurrency and restore |
| Upload, hash, version, chunk, publish, replace/delete, ingestion worker | Yes | Markdown upload, publish, replace/delete retrieval invalidation passed in API test | PDF/CSV, retry, source drawer and broader browser checks |
| React console and customer widget | Yes | `pnpm check` passed build, 26 AST OpenAPI route/method checks, and upload form fields; browser upload/publish → cited widget answer, new proposal/review/record, ticket reply/resolve, ingestion cancel, SSE, and unsupported-answer paths reported passed; eight saved screenshots at 1440/1024/390 px | Complete accessibility and response-type checks |
| One-command local launch | Yes | Windows prepare and timed full launch passed, including direct/proxy health | POSIX runtime check |
| PostgreSQL/pgvector and checkpoint deployment | Compose, Alembic, checkpoint setup script present | `docker compose config --quiet` passed; no Docker daemon or database run | Image build, migration, setup, backup/restore, concurrency |
| OpenAI, Shopify, Zendesk live behavior | Adapter/configuration, scoped Shopify order mirror, and leased Zendesk ticket synchronization code present | Shopify/Zendesk mock contract tests passed; no live calls | Bounded live smoke tests; USD-only Shopify mirror and 100-line/fulfillment cap |
| Held-out DEMO graph assessment | Yes | Grounded structured claims 60/60, grounded citation IDs 60/60, all emitted citation IDs 89/104, clarification 12/12; local graph p50/p95 73.31/87.4945 ms | Human citation-span review; connected-model cost and latency |
| SQLite retrieval comparison | Yes | 80 grounded cases: hybrid acceptable source top 1 at 80/80 versus lexical baseline 69/80; p50/p95 12.08/12.83 ms versus 10.93/11.52 ms | Repeat on PostgreSQL/pgvector |
| Scoped retention cleanup | Narrow CLI with dry-run default and explicit apply | Disposable two-workspace SQLite dry-run/apply scope check passed; no apply on shared DEMO | Schedule and extend to checkpoints, backups, chunks, and all data copies |

This table is intentionally narrower than the product requirements. Read [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for exact pending checks and [EVALUATION.md](EVALUATION.md) for quality targets.

## Verification record

From `apps/api`, the backend commands `uv run ruff check src/supportpilot tests ../../evals/run_demo.py`, `uv run mypy src/supportpilot --follow-imports=silent --ignore-missing-imports`, and `uv run pytest -q` passed; pytest reported **23 passed**. The SQLite review test creates a paused checkpoint in a child Python process, exits it, then issues two concurrent approvals from the parent and checks one return/audit result. The staff boundary test denies another workspace's conversation, order, source, document list item, proposal review, and return proposal; customer tests deny foreign and same-workspace other-customer orders. From `apps/web`, `pnpm check` passed the build and AST verification of 26 client route/method pairs plus upload multipart fields against OpenAPI. CI is configured to export the API schema as an artifact and run `pnpm check` in the web job; that remote workflow has not yet run here. The browser agent saved eight views under `apps/web/screenshots/`, including [desktop inbox](../apps/web/screenshots/01-inbox-desktop.png), [source passage](../apps/web/screenshots/02-source-passage.png), [approval review](../apps/web/screenshots/06-approval-review.png), [tablet inbox](../apps/web/screenshots/09-inbox-tablet.png), and [mobile widget](../apps/web/screenshots/08-widget-mobile.png). Their verified dimensions are five at 1440×900, one at 1024×768, and two at 390×843.

The browser acceptance run created a **new** `opened_equipment` return proposal from Inbox conversation `conv_ns_0138` for order `ord_ns_01909`. Proposal `d2b89320-4b6e-492f-ac4b-7312cf3520ea` appeared as Pending Review; approval in the Approvals UI displayed Recorded with return record `6234f498-b4a5-433f-bc3e-913a6450c412`. Those UUIDs belong to this run and will change after a DEMO reset. This is distinct from approving a pre-seeded proposal. The browser QA also recorded successful upload → publish → cited answer, a queued-job cancellation returning the document to draft, grounded chat, a new ticket with verified order/shipment context shown in desktop and mobile UI, ticket reply/resolve, widget SSE, unsupported-answer, and 1440/1024/390 viewport checks.

For a causal retrieval check, the browser agent uploaded and published `browser-qa-policy.md`, then asked a related question in the customer widget. The answer cited that newly uploaded document. The updated [mobile widget screenshot](../apps/web/screenshots/08-widget-mobile.png) records the result. This establishes the local DEMO upload-to-answer path for that document, separate from pre-seeded knowledge.

A fresh SQLite database at `data/migration_verify_d632.db` migrated through revision `d632a74041e8`; `alembic check` then reported “No new upgrade operations detected.” This checks migration completeness for SQLite, not PostgreSQL/pgvector deployment.

The final synthetic run is recorded in `evals/results/model_run.json`: 120/120 held-out coverage, 60/60 grounded structured claims and citation version IDs, and 89/104 (85.6%) precision across all emitted citation IDs. The brief's 95% citation target is scoped to grounded questions, where the ID proxy passed; whether the exact cited passages support the grounded answers remains unreviewed. The broader all-category result is a warning, not the target denominator. This is a structured DEMO proxy, with no human passage review, no paid model call, and no first-token measurement. The separate SQLite retrieval report is in `evals/results/retrieval_comparison.json`. See [EVALUATION.md](EVALUATION.md) for all denominators and scope limits.

CONNECTED composition is capped at one model call with no automatic retry, a 25-second timeout, a default 700 output-token limit, and bounded question/order/evidence character lengths. A `model_usage` event records provider token counts if supplied, with known/partial/unknown status and no source text. Dollar cost remains unknown and no application dollar cap exists. The narrow [retention CLI](OPERATIONS.md#retention-and-monitoring) preserves conversation shells and ticket/return audit threads; it does not clear checkpoints, backups, published files, chunks, or every personal-data copy.

## Customer-specific next steps

Set a unique secret and HTTPS secure cookies; choose PostgreSQL/pgvector and initialize checkpoints; configure backups and retention; supply buyer-approved policies/catalog; map authenticated customers and order IDs; set return rules and source authority; wire and test selected live connectors with a bounded budget; complete access, retry, browser, and held-out human-review gates. Do not publish the demo data or claim production readiness from synthetic tests alone.
