# SupportPilot — independent portfolio case study

**Project type:** Independent portfolio project. Northstar Supply and Harbor Workroom are fictional. All displayed people, orders, policies, and revenues are synthetic. This is a self-hostable pilot foundation, not a delivered customer engagement or a measured production deployment.

## Problem and approach

Retail support agents need to answer catalog and policy questions while checking the right customer's order. Unsupported claims, stale policies, and unauthorized order lookups can make a helpful chat unsafe. SupportPilot presents the source passage beside the answer, binds order tools to server-side identity, turns exception requests into version-bound operator decisions, and keeps a local action record for retries. The same workspace holds conversations, knowledge health, approvals, and tickets.

The implementation combines FastAPI, SQLAlchemy/Alembic, LangChain document processing, LangGraph chat/review flows, and a React/TypeScript console. A deterministic demo mode exercises the business workflow without sending external messages or moving money. Connected model and connector paths require credentials and separate verification. The full synthetic generator produces 2 isolated workspaces, 120 products, 800 customers, 3,000 orders, 80 documents, 400 conversations, and 40 seeded proposals. The 160-case evaluation set has a 40/120 development/held-out split. Fixture integrity, local DEMO graph structured predictions, a SQLite retrieval comparison, backend tests, and browser smoke journeys were recorded. Human passage review and connected-model performance remain unmeasured.

## Planned 60–90 second demo script

**0:00–0:12 — Customer widget.** On screen: sign in as `ns.customer.0001@example.test`, open Customer widget, and point to the synthetic label. Say: “This is Northstar Supply's fictional storefront support workspace. Every order and customer here is generated for the demo.”

**0:12–0:28 — Evidence.** On screen: ask about the monitor return rule and open a source. Say: “The assistant links its answer to a published policy passage. The drawer shows the exact text, version, and effective interval, so an agent can check where a claim came from.”

**0:28–0:48 — Order and action.** On screen: open `ord_ns_demo_001`, showing the promise of August 14 and delivery on August 26; inspect or draft the linked proposal. Say: “This monitor arrived twelve days late. Its normal return period has passed, but the late-delivery rule permits an exception request. The server calculates that rule; the model does not approve the action.”

**0:48–1:08 — Review.** On screen: sign in as `operator.ns@example.test`, review the version-bound card, and approve once. Say: “An operator sees the reason and consequence before approval. Repeating the same local approval points to one recorded return. No refund or external message is sent.” If a previous run already processed the proposal, reset only the demo namespace or create a new proposal before recording.

**1:08–1:20 — Limits and handoff.** On screen: ask an undocumented compatibility question, show clarification, then open a ticket. Say: “When evidence is missing, the assistant asks for the laptop model. An unresolved case can be handed to a person with its context. Connected-model quality and the cited passages still need human review.”

This is a recording outline, not a completed video. Browser QA created a fresh return proposal through the UI and recorded it after operator approval; saved screenshots are listed below. Rehearse the chain again before recording a shareable demo.

## Planned 3–5 minute technical walkthrough

**0:00–0:40 — System boundary.** Show `apps/api/src/supportpilot` and `apps/web/src/features`, then the architecture graph. Explain: “This is one FastAPI service with capability modules and one React client. A customer session establishes identity before any AI step. Workspace IDs scope records, source passages, approvals, and checkpoints. The local run uses SQLite and a file checkpoint; PostgreSQL with pgvector is present in migrations but still needs deployment verification.”

**0:40–1:30 — Knowledge lifecycle.** Show the Knowledge page, `knowledge.py`, and a source drawer. Explain: “An admin upload is checked for type and size, hashed, stored under its workspace, then extracted into PDF pages or text sections. A persisted job chunks and indexes it; publication is a separate step. Retrieval checks the workspace, publication state, and effective interval. Historical policy questions can select a dated version. A cited chunk must be in the retrieval result, and the source endpoint checks its publication again when someone opens it. On 80 synthetic grounded questions, the SQLite hybrid path put an acceptable source first in 80 cases versus 69 for lexical baseline; PostgreSQL/pgvector still needs a run.”

**1:30–2:15 — Authenticated tools.** Show the order API query and local/Shopify adapter boundary. Explain: “The customer's ID comes from the session and conversation, never from the message. A typed order number only narrows the query within that identity. The demo guest challenge reveals a simulated code locally; it does not contact a real person, and it is disabled in connected mode. A production buyer needs a real verification channel with rate limiting. The Shopify adapter is read-only and requires a verified customer email supplied by the server.”

**2:15–3:15 — Return safety.** Show `domain.py`, `review_graph.py`, and `returns.py`. Explain: “Eligibility is a deterministic function of delivery date, category, quantity, prior returns, condition, and workspace policy. The proposal version hashes the exact request and policy result. LangGraph pauses for review, but the action node rechecks operator role, workspace, version, expiry, and remaining quantity. The local ledger and unique return record make a repeated approval return one result. For a third-party timeout, the adapter must reconcile by external ID before any retry; local idempotency is not a promise of exactly-once behavior across providers.”

**3:15–4:00 — Evidence and limits.** Show the evaluation page and `evals/cases.jsonl` without opening the ground-truth answers in a runtime prompt. Explain: “The generator builds 160 cases, including missing evidence, identity attacks, and historical policy dates. Forty are for development and 120 are held out. The DEMO graph returned 160 predictions without execution errors. On held-out grounded questions, structured claims and citation version IDs matched 60 of 60. Across all categories, emitted citation IDs matched 89 of 104. Those automated checks do not prove passage support. Release claims require human-reviewed cited spans, connected-model measurements, PostgreSQL restore/concurrency, and bounded live connector tests.”

## Three content angles

- **Evidence that survives document change:** versioned sources, effective dates, clickable passages, and stale-citation invalidation.
- **Identity before tools:** server-bound customer identity and workspace scoping even when the chat prompt asks for a foreign order.
- **Human review as a durable workflow:** exact proposal versions, pause/resume, deterministic eligibility, and an idempotent local action record.

## Screenshots and resume material

The browser agent saved eight screenshots: five desktop files at 1440×900, one tablet inbox at 1024×768, and two mobile files at 390×843. The tablet view was visually checked for overlap.

One browser acceptance run started from Inbox conversation `conv_ns_0138` and order `ord_ns_01909`, created a new `opened_equipment` proposal (`d2b89320-4b6e-492f-ac4b-7312cf3520ea`) with Pending Review status, then approved it in the Approvals UI and observed Recorded with return record `6234f498-b4a5-433f-bc3e-913a6450c412`. These UUIDs are run-specific. In a separate causal knowledge check, the browser QA uploaded and published `browser-qa-policy.md`, then observed a customer-widget answer citing that new document; the updated mobile-widget screenshot captures it. Ticket reply/resolve, widget SSE, and an unsupported answer were also exercised.

| View | Saved artifact |
|---|---|
| Desktop inbox | [01-inbox-desktop.png](../apps/web/screenshots/01-inbox-desktop.png) |
| Source passage | [02-source-passage.png](../apps/web/screenshots/02-source-passage.png) |
| Mobile inbox | [03-inbox-mobile.png](../apps/web/screenshots/03-inbox-mobile.png) |
| Knowledge | [04-knowledge-desktop.png](../apps/web/screenshots/04-knowledge-desktop.png) |
| Tablet inbox | [09-inbox-tablet.png](../apps/web/screenshots/09-inbox-tablet.png) |
| Approval review | [06-approval-review.png](../apps/web/screenshots/06-approval-review.png) |
| Ticket handoff | [07-ticket-handoff.png](../apps/web/screenshots/07-ticket-handoff.png) |
| Mobile widget | [08-widget-mobile.png](../apps/web/screenshots/08-widget-mobile.png) |

Resume bullets supported by current fixture measurements:

- Built an independent FastAPI/React support pilot with deterministic synthetic data spanning 2 isolated workspaces, 3,000 orders, 80 knowledge documents, and 400 historical conversations.
- Designed a 160-case evaluation dataset with 40 development and 120 held-out cases; automated fixture validation passed for counts, scoped references, totals, source IDs, and label separation.
- Implemented and tested a version-bound review flow; a 23-test backend suite passed, including staff cross-workspace denial, unauthorized customer order reads, a child-process checkpoint restart followed by concurrent approval, source priority, document invalidation, and mocked connector reconciliation.
- Completed a browser fresh-proposal journey from customer order to operator approval and recorded return, plus upload/publish, grounded answer, and human ticket paths on the synthetic DEMO.
- Measured 80 SQLite grounded retrieval cases: hybrid source at rank 1 in 80/80 versus 69/80 for the lexical baseline. The 160-case DEMO graph run recorded 60/60 held-out grounded structured claim matches and citation version IDs; human cited-passage review remains pending.

Do not present fixture counts as customer traffic, local DEMO latency as connected-model latency, or automated source-ID matches as the brief's reviewed 90%/95% quality targets. Add customer-outcome and live-integration bullets only after those measurements exist.

