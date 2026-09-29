# Security model and deployment gaps

SupportPilot is designed as one customer installation with workspace-scoped data. The synthetic seed includes two workspaces to exercise boundaries. Server-side session state, rather than a prompt-supplied order number or LangGraph thread ID, establishes identity. Passwords are hashed with Argon2 when imported; the fixture contains a known **demo-only** password and must never be reused for a real installation.

## Implemented controls

- HTTP-only, `SameSite=Strict` session cookie with a hashed token stored in the database and an expiry. `COOKIE_SECURE` is configurable; enable it for HTTPS deployment.
- Admin, operator, viewer, and customer roles. The API checks role and workspace on document, source, conversation, order, ticket, and approval endpoints. A customer order lookup also checks owner ID. Role and current business state are rechecked when reviewing an action.
- Admin onboarding endpoints scope customer accounts, catalog records, and local orders to the signed-in workspace. Customer passwords are hashed, duplicate emails/SKUs are rejected, and an unclassified mirrored product cannot pass return eligibility until its category is set. For split orders without line-to-shipment mapping, every shipment must be delivered; policy timing uses the earliest delivery and excludes the late-delivery exception. Approval revalidates current eligibility.
- Document uploads accept only PDF, Markdown, or CSV up to a configured size. PDF signatures are checked, source bytes are SHA-256 hashed, and stored files are under workspace/document directories. CSV and Markdown are parsed as data. The client renders source text as text rather than injecting source HTML.
- Retrieval selects workspace-scoped, published, date-effective document versions. Returned citation IDs are checked against actually retrieved chunks, and the source endpoint revalidates publication before showing a current or historical passage with its effective interval.
- A return proposal is version-bound. The action ledger and unique return record protect the local side effect against repeated clicks. Ticket connector delivery has a separate ledger key, five-minute claim lease, and deterministic external ID; uncertain writes are marked for reconciliation rather than blindly replayed. Escalation includes only orders that match both the workspace and the conversation customer.
- Connector destinations have allowlisted shapes: Shopify shops must end in `.myshopify.com`; Zendesk uses a constrained subdomain. Tokens remain in server configuration.
- CONNECTED composition makes at most one model call with no automatic retry, a 25-second timeout, a default 700 output-token cap, bounded question/order/evidence lengths, and per-passage clipping. Provider token counts, when supplied, enter a `model_usage` event with known/partial/unknown status; that event does not contain source text. It does not impose a dollar spending cap.

## Demo-only behavior

The guest challenge returns its code in the API response with an explicit synthetic notice and sends no email or SMS. It is disabled in CONNECTED mode. It is suitable only for local demonstrations. The default `SECRET_KEY` and insecure cookie setting are local defaults; CONNECTED startup rejects the default secret, but a deployment must also enforce HTTPS, secure cookies, and secret rotation. Demo source documents, names, orders, and revenues are fictional.

## Gaps before customer deployment

1. Add a real guest verification channel with rate limiting and non-enumerating responses. The current demo challenge exposes whether the supplied order/email pair exists through its result.
2. Add CSRF protection appropriate for cookie-authenticated mutating requests, edge rate limiting, and a reverse-proxy/TLS configuration. The repository does not yet demonstrate these controls.
3. Complete retention and deletion across backups, checkpoints, document chunks/version metadata, tickets, and all personal-data copies; define a schedule, trace redaction, access logging, and incident response. The dry-run-first [purge CLI](OPERATIONS.md#retention-and-monitoring) can remove old messages/events from resolved audit-unlinked conversations, expired workspace sessions, and old soft-deleted raw upload files. It preserves conversation shells and ticket/return-linked threads and is not a full data-erasure or compliance workflow. Soft deletion alone removes retrieval access but leaves stored material until this limited purge runs.
4. Contract-test every configured live connector against a bounded sandbox account and verify that ambiguous writes reconcile. The Zendesk adapter is wired through local ticket synchronization, but no live accounts were used here. Review buyer permission to send verified order context, tracking, and evidence references to the external ticket system.
5. Verify PostgreSQL row-level access assumptions, migrations, checkpoint setup, backup/restore, concurrency, and permissions. SQLite local checks do not prove those behaviors.
6. Threat-test prompt injection, malicious PDFs/CSV, citation forgery, cross-workspace access, stale citations, and repeated approvals with the full browser/API flow. The system prompt treats source content as untrusted, but that alone is not a proof of safety.

No secrets belong in `.env.example`, screenshots, traces, fixtures, or this documentation. Never index `evals/ground_truth.jsonl` into a runtime knowledge base. The measured access and concurrency test status is tracked in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).
