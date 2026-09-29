# API contract

The FastAPI application exposes `/openapi.json` and `/docs` when running locally. All paths below are relative to `/api`. The web client sends the `supportpilot_session` HTTP-only cookie with requests. A 401 means sign-in is required; a 403 means the role cannot perform the operation; scoped missing resources return 404 without revealing whether another workspace or customer owns them. Validation errors use 422, proposal version conflicts use 409, and a failed assistant run uses 503 after saving the customer message.

| Resource | Methods and paths | Access and effect |
|---|---|---|
| Health | `GET /health` | DB connectivity, mode, dialect |
| Session | `POST /auth/login`, `GET /me`, `POST /auth/logout` | Password login and revocable session cookie |
| Admin onboarding | `GET/POST /admin/customers`, `GET/POST /admin/products`, `PATCH /admin/products/{id}`, `POST /admin/orders` | Admin only, workspace scoped. Create a customer login, catalog product, or local order with lines/shipments; set a specific product category before return eligibility. Local order creation is disabled when Shopify is the commerce source. |
| Conversations | `GET/POST /conversations`, `GET /conversations/{id}`, `POST /conversations/{id}/messages`, `POST /conversations/{id}/messages/stream` | Customer owns own conversations; staff see workspace conversations. The stream emits `message`, `answer_chunk`, and `final` SSE events after the graph has produced the complete answer. |
| Orders | `GET /orders/{id}` | Workspace and customer ownership checks |
| Guest demo verification | `POST /guest/challenges`, `POST /guest/challenges/{id}/verify` | Local simulated challenge only; no external message |
| Knowledge | `GET/POST /documents`, `POST /documents/{id}/versions`, `/publish`, `/retry`, `DELETE /documents/{id}`, `POST /ingestion-jobs/{id}/cancel` | Staff list; admin mutations. Upload accepts a file plus optional `category` and `authority` form fields. Pending jobs cancel immediately; a running job records a cancellation request that its worker checks. Publish activates the new effective interval while preserving dated history. |
| Ingestion events | `GET /documents/jobs/{id}/events` | Staff SSE progress; event type `progress` |
| Evidence | `GET /sources/{chunk_id}` | Revalidates published source in workspace; historical versions carry an effective interval |
| Returns | `GET /proposals`, `POST /returns/proposals`, `POST /proposals/{id}/review` | Customer or staff proposes; admin/operator reviews exact version |
| Handoff | `POST /conversations/{id}/escalate`, `GET /tickets`, `POST /tickets/{id}/reply`, `POST /tickets/{id}/status`, `POST /tickets/{id}/sync` | Escalation persists a local ticket before connector delivery. Its `order_context` contains only verified or mentioned orders matched to the conversation customer within the workspace. Admin/operator sync reconciles or retries; the response includes `external_ticket_id` and `sync_status`. |
| Operations | `GET /connectors`, `GET /evaluations/summary` | Staff-only status and recorded evaluation data |

Representative request to draft a return:

```json
{"order_id":"ord_ns_demo_001","line_id":"line_ns_demo_001","quantity":1,"condition":"unopened","reason":"Monitor arrived 12 days after the promised date","conversation_id":"conv_ns_demo_001"}
```

The response includes `proposal`, `policy_result`, `status`, `requires_review`, `version`, and `idempotent_replay`. Review uses `{"decision":"approve","version":"<current proposal version>"}`; `edit` also requires `edited_reason`. The server rechecks role, workspace, version, expiration, quantity, and policy before executing. It returns the existing local return record for an exact replay. The demo never initiates a refund.

For split shipments, shipment rows currently have no order-line mapping. The return API requires **all** shipments on the order to be marked delivered before evaluating a line; otherwise it records a non-executing `not_delivered` proposal, and approval is rejected. Once all are delivered, the policy window uses the **earliest** recorded delivery date, a conservative limit when the selected line's parcel is unknown. The promised-date late-delivery exception is disabled for split orders. Approval rechecks these facts and current eligibility. Customer-specific split-delivery rules need review before deployment.

For a message response, `assistant` includes `content`, `citations`, `next_action`, and `missing_information`. Each citation identifies a retrieved chunk, title, version, section, optional page, and passage. `GET /sources/{chunk_id}` checks that the passage is still published and returns `historical`, `effective_from`, and `effective_to`; deleted sources remain inaccessible. The message SSE endpoint chunks a completed answer into 96-character `answer_chunk` events; it is not model-token streaming, and first-token model latency is not measured. `apps/web/src/lib/api.ts` is hand maintained. `pnpm check` verifies its 26 route/method pairs and document multipart fields (`file`, `category`, `authority`) against OpenAPI with an AST check; it does not validate response types. A generated OpenAPI TypeScript client is pending.

Ticket creation uses a local support adapter by default. When `SUPPORT_ADAPTER=zendesk` is configured in CONNECTED mode, the API searches by deterministic external ID before creating a Zendesk ticket. A connector failure leaves the local ticket available and returns 503 from escalation or sync; an in-progress five-minute ledger lease returns 409. A timeout marks the write `uncertain` and clears the lease, so an operator can call `/tickets/{id}/sync` to reconcile by external ID. The ticket body includes the scoped order context, attempted steps, unresolved questions, and evidence references. Operator replies and status changes currently update the local conversation/ticket only; they are not pushed to Zendesk. The connector code path has not been verified against a live Zendesk account.

For document upload, `category` is a lowercase identifier up to 50 characters and `authority` is one of `official_policy`, `product_manual`, `faq`, `support_guide`, or `uploaded`. If omitted, authority is inferred from `faq` or `manual` in the filename, then from policy categories (`returns`, `shipping`, `warranty`, `orders`), otherwise `uploaded`. A replacement version keeps its document's existing category and authority. Workspace `policy_priority` orders conflicting source authorities in the answer flow.

The evaluation endpoint reads `model_run.json` when present and otherwise returns `fixture_validation.json` from `evals/results`. The frontend labels structured prediction assessment separately from fixture integrity. Read [EVALUATION.md](EVALUATION.md) for the runner contract and measured state.
