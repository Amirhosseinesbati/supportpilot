# Commercialization notes

## Buyer and offer

The likely buyer is a premium equipment retailer with a meaningful product catalog, written return/warranty rules, a support team, and a commerce platform whose authenticated customer data can be connected. The offer is an **installed support assistant** configured to its documents and systems, plus setup, evaluation, and ongoing maintenance. It is a starting point for installation/customization work, not a public self-service SaaS subscription or a replacement for the whole support team.

## Customer onboarding

1. Confirm data owner, hosting region, retention period, support roles, customer identity method, and the permitted order/ticket integrations.
2. Deploy an isolated database, backup location, HTTPS reverse proxy, and secret store. Replace every demo credential and the default secret; disable synthetic seed/reset in CONNECTED mode.
3. Create the initial admin with the connected bootstrap, then use workspace-scoped admin APIs to create customer logins, products, and local orders with lines/shipments. With Shopify selected, create or map the customer identity first; the read-only external lookup verifies the server-resolved customer email and mirrors a matching order locally. Unknown Shopify SKUs need an admin category before return eligibility. Match account identity without using a prompt-supplied email or order number as authorization.
4. Collect approved manuals, policy PDFs, Markdown FAQs, and product CSVs. Record authoritative source priority, effective dates, and who may publish updates. Review extraction and citation passages.
5. Encode the customer's deterministic return rules and review exceptions with its policy owner. Verify sample decisions at boundaries, previous-return quantities, and ambiguous shipping timelines.
6. Configure a model ID and connector credentials server-side and set a small external provider spending limit for a smoke test. The application bounds one model call with a default 700-output-token cap and input-character limits, while a dollar cap remains to be implemented. Run adapter contract tests and a small bounded live smoke test with an account the buyer controls.
7. Run the synthetic evaluation first, then a customer-approved held-out set with human review. Resolve unsupported answers, stale sources, access leaks, and action retries before a limited launch.
8. Train operators to edit/reject proposals, reconcile uncertain external writes, respond through tickets, and restore from a backup. Document a rollback path and incident contact.

## Reusable modules

The versioned ingestion pipeline, evidence passage drawer, scoped order port, return policy function, version-bound approval workflow, action ledger, and local commerce/support simulators are reusable. Customer-specific work remains in policy rules, document authority, identity mapping, branding, and external adapter credentials/schema mapping.

## Cost model

Use the buyer's actual provider contract and expected traffic. A configurable monthly estimate is:

`model cost = conversations × ((average input tokens × input rate per million + average output tokens × output rate per million) / 1,000,000)`

Add database storage, uploaded documents, backups, compute, logging, connector platform fees, and operator review time. For an **illustrative assumption only**, 10,000 conversations/month at 2,000 input and 400 output tokens, hypothetical rates of $2 and $8 per million tokens, produce `$40 + $32 = $72` in model charges. Hypothetical 10 GB database, 20 GB uploads, and 20 GB backup at $0.10/GB-month add $5, giving **$77/month before compute, network, connector, and labor costs**. These are arithmetic examples, not current vendor quotes or a price promise. Replace every input with current contracted rates before offering a proposal; an application per-run dollar cap and measured provider billing are not implemented yet.

## Supported scope and limits

The local install supports synthetic commerce data and local tickets. A Shopify read-only external adapter mirrors verified orders into local scoped records; it currently requires USD, fails closed above 100 order lines/fulfillments, and needs manual category configuration for unknown SKUs. A Zendesk ticket-create adapter is wired through local ticket persistence, a leased action ledger, and external-ID reconciliation. Operator replies and status changes remain local. Neither connector has been verified with live credentials. No actual refund or payment transaction occurs. Multilingual knowledge, email channel, advanced SLA routing, and real refund integration are later work. PostgreSQL, checkpoint setup, TLS/security hardening, tenant-specific retention, human-reviewed quality, and license review are outstanding deployment requirements. Browser DEMO smoke journeys passed, but connected deployment and live customer behavior remain unverified. Do not sell the current tree as production-ready until those gates are verified.
