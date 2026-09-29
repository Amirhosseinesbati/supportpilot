# Operations and local launch

## Prerequisites and demo launch

Use Python 3.12, `uv`, Node.js 24, and pnpm 11.19.0. The frontend serves at `http://localhost:5173` and proxies `/api` to `http://localhost:8000`. The default DEMO database is SQLite under `apps/api/data`; the demo launch scripts generate a missing synthetic fixture, migrate and seed on first launch, then start both services. They preserve an existing database unless reset is requested. They are intended for local use only. Windows `-PrepareOnly` and a timed full launch with alternate ports were verified on this host; the Bash script passed a syntax check but has not run on POSIX here.

Windows PowerShell:

```powershell
Set-Location '/path/to/supportpilot'
pwsh -File scripts/demo.ps1 -Size full
```

POSIX shell:

```bash
cd /path/to/supportpilot
bash scripts/demo.sh full
```

If a launch script is unavailable, use two terminals after generating the data and installing dependencies:

```powershell
python scripts/generate_demo.py
python scripts/generate_evals.py
Set-Location apps/api
uv sync --locked
uv run python -m supportpilot.seed --size full --reset
uv run uvicorn supportpilot.api:app --host 127.0.0.1 --port 8000
```

```powershell
Set-Location apps/web
pnpm install --frozen-lockfile
pnpm dev
```

The seed command's `--reset` replaces only the fixture's demo workspaces, their workspace-prefixed SQLite checkpoint threads, and their upload directories. DEMO seeding refuses to run in CONNECTED mode. Do not point the demo reset at customer records. Use `--size small` for a fast UI check. The full fixture is generated and ignored by Git; [DATA_CARD.md](DATA_CARD.md) records its exact counts and reference date. Local login details are in [HANDOVER.md](HANDOVER.md).

For a non-serving setup run, use `pwsh -File scripts/demo.ps1 -Size full -PrepareOnly` or `bash scripts/demo.sh full --prepare-only`. The PowerShell script also supports `-ApiPort`, `-WebPort`, and `-RunSeconds` for a bounded launch check; it refuses occupied ports and stops its child processes on exit.

The launch scripts set `UV_CACHE_DIR` to the project `.uv-cache` when it is unset. For standalone `uv` commands on a host with an inaccessible default cache, set `UV_CACHE_DIR` to that writable project directory first.

## Configuration

Set API environment variables in `apps/api/.env` or the process environment. Relevant keys are `APP_MODE`, `DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE`, `UPLOAD_ROOT`, `MAX_UPLOAD_BYTES`, `REFERENCE_DATE`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `MODEL_MAX_OUTPUT_TOKENS`, `MODEL_MAX_INPUT_CHARS`, `MODEL_MAX_PASSAGE_CHARS`, `COMMERCE_ADAPTER`, `SHOPIFY_SHOP_DOMAIN`, `SHOPIFY_ACCESS_TOKEN`, `SHOPIFY_API_VERSION`, `SUPPORT_ADAPTER`, `ZENDESK_SUBDOMAIN`, `ZENDESK_EMAIL`, and `ZENDESK_API_TOKEN`. Do not commit credentials. `APP_MODE=CONNECTED` rejects the default demo secret and raises an error when the selected model lacks a key; it does not silently fall back to a demo answer. Set `COOKIE_SECURE=true` behind HTTPS before exposing the service beyond localhost.

CONNECTED composition makes at most one model call with no automatic model retry, a 25-second timeout, a default 700 output-token cap, and a 16,000-character human-message limit. The question is clipped to 4,000 characters, scoped order context to 3,000, evidence to 8,000, and each passage to 1,000; the limits are configurable as above. A `model_usage` event records provider token counts when returned, with `known`, `partial`, or `unknown` status and no source text. Dollar cost remains unknown because no model pricing or spend enforcement is configured; set an external provider spending limit for a bounded smoke test.

`COMMERCE_ADAPTER=local` reads local scoped orders. `COMMERCE_ADAPTER=shopify` reads Shopify using a server-resolved customer email and an exact order number, then mirrors a verified order, lines, and shipments into scoped local records for support/return work. It never writes to Shopify. The current mirror accepts USD only, rejects orders with more than 100 lines or fulfillments until pagination is added, and creates unknown SKUs as `unclassified`; an admin must set their category before return eligibility. `SUPPORT_ADAPTER=local` records a local provider ID; `SUPPORT_ADAPTER=zendesk` in CONNECTED mode sends a committed local ticket to Zendesk using an external ID, subject, summary, verified order context, attempted steps, unresolved questions, and evidence references. Subsequent operator replies and status changes remain local. Bounded live smoke tests are still pending. The connector page reports configuration state, not verified end-to-end service health.

## Connected Compose setup

The root `docker-compose.yml` defines PostgreSQL 17 with pgvector, API, and web services. Copy `.env.example` to `.env`, set a URL-safe `POSTGRES_PASSWORD`, a unique `SECRET_KEY`, and `OPENAI_API_KEY`, then run `docker compose up --build -d`. The API container applies Alembic migrations and invokes `scripts/init_checkpoints.py`, which calls LangGraph `PostgresSaver.setup()`, before serving requests. Use `docker compose exec api python scripts/bootstrap_connected.py --workspace "Customer Name" --email "admin@example.com"` to create one empty workspace and admin; it prompts for a password of at least 16 characters and refuses a second workspace. The bootstrap requires CONNECTED mode and PostgreSQL and imports no synthetic data. The new admin can use `POST /api/admin/customers`, `POST /api/admin/products`, and `POST /api/admin/orders` to create a local pilot catalog and customer orders; `PATCH /api/admin/products/{id}` sets category for a mirrored unknown Shopify SKU. These API routes are workspace scoped and have no dedicated onboarding UI. Set optional Shopify and Zendesk credentials only for the adapters selected by `COMMERCE_ADAPTER` and `SUPPORT_ADAPTER`. `docker compose config --quiet` passed with placeholder required variables on this host. The Docker daemon was unavailable, so image build, PostgreSQL migration, checkpoint setup, and live Compose integration have not been verified.

## Jobs, retries, and recovery

An ingestion job is stored with status, progress, error, attempts, cancellation request, and a lease. The API process starts one background worker that claims pending jobs or running jobs whose lease expired. A stopped API process does not process jobs; restart the API to recover the queue. An admin can cancel a pending job immediately or request cancellation of a running job; the worker checks between extracted sections. The UI offers cancel and retry for failed or cancelled jobs. The SSE endpoint `/api/documents/jobs/{id}/events` reports persisted progress. To recover a failed PDF, inspect its job error, correct the file, replace or retry through the admin UI, wait for completion, and publish the new version. Deletion and replacement should be verified by reopening old citations and running a retrieval check after indexing completes.

Human review is durable through a LangGraph checkpoint saver. A proposal version is checked again on review; refresh if the server returns 409. If a local action is already recorded, an exact repeated approval returns the same record. For split shipments, a return cannot execute until every shipment on the order is marked delivered; then eligibility uses the earliest delivery date and no late-delivery exception. Line-to-shipment attribution is unavailable, so review customer-specific timing rules before deployment. Approval rechecks current eligibility, including shipment and category state. Escalation commits a local ticket with scoped order context and attempts support-adapter delivery. A connector failure returns 503 while preserving the local ticket; inspect its `sync_status`. An uncertain outcome can be retried with `POST /api/tickets/{id}/sync` by an admin or operator, which searches the provider's external ID before create. A claimed sync holds an explicit five-minute lease and returns 409 until it expires; retry then reconciles by external ID. Never assume a timeout means the provider did nothing.

## Backup and restore

For the **local SQLite demo**, stop both services before file-level backup so WAL and checkpoint writes are quiescent. Preserve the entire `apps/api/data` directory, including `supportpilot.db`, `supportpilot.db.checkpoints`, and `uploads/`. Keep the backup outside the served web directory, encrypt it if it contains customer-specific data, and record the application version and timestamp. Copying only the main `.db` while the process runs is unsafe. Restore into an **isolated copy** of the checkout with the same relative `data/uploads` layout; start the API, call `/api/health`, sign in, open a known order and source passage, then resume a pending review in that copy. Do not run a restore smoke test against the working demo database.

For **PostgreSQL deployment**, configure an independent database and initialize both Alembic tables and the LangGraph PostgreSQL checkpoint schema before first use. The Compose startup calls `scripts/init_checkpoints.py`; its execution against PostgreSQL remains unverified. Use a consistent `pg_dump --format=custom` backup and `pg_restore` into a disposable database; preserve the upload directory in the same backup set. Verify row counts, one scoped order, one cited passage, and one pending approval after restore. PostgreSQL/pgvector migration, concurrent-worker behavior, and restore have not been tested on this host.

## Retention and monitoring

`scripts/purge_content.py` is a **narrow, operator-run cleanup**, dry-run by default. Stop API/worker processes, take a recoverable backup, select the exact workspace ID and an approved UTC cutoff, and inspect its JSON preview before adding `--apply`. From `apps/api`:

```powershell
uv run python ../../scripts/purge_content.py --workspace-id 'workspace-id-from-bootstrap' --before 2026-01-01
uv run python ../../scripts/purge_content.py --workspace-id 'workspace-id-from-bootstrap' --before 2026-01-01 --apply
```

It deletes messages and events older than the cutoff only from **resolved conversations last updated before the cutoff** that have neither a ticket nor a return proposal. It leaves their conversation shell and all ticket/return-linked threads for audit. It also deletes that workspace's sessions whose expiry predates the cutoff and raw upload files belonging to documents soft-deleted before it. File paths must be direct files within `UPLOAD_ROOT/<workspace-id>/<document-id>/`; unsafe or symlinked paths make `--apply` refuse all deletion. A disposable two-workspace SQLite check passed both dry-run/no-change and apply/scope assertions via `uv run python ../../scripts/check_purge_content.py`. No destructive apply was run on the shared DEMO database.

This CLI does **not** purge checkpoints, backups, still-published files, document chunks/version metadata, tickets, proposals, action ledgers, active conversations, or every personal-data copy. Raw-file deletion and database deletion are separate operations; if a file removal fails after the database commit, review the error and rerun. Define a customer-specific retention schedule and backup expiration policy before deployment. The service exposes `/api/health` and records scoped events and provider token usage when available, but scheduled purge, redacted trace controls, dollar cost accounting, and alerting are incomplete. Keep tracing disabled unless its data handling has been reviewed. Watch failed ingestion jobs, 503 assistant responses, 409 review conflicts, and external connector timeouts; record workspace and run IDs without logging secrets or full sensitive content.
