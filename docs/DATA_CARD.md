# Synthetic demo dataset — data card

This is a **Synthetic demo dataset** for the fictional premium home-office retailer Northstar Supply and a separate fictional installation, Harbor Workroom. No record is a real customer, order, revenue figure, testimonial, or production policy. Email addresses use `example.test`; shipment codes and carrier names are explicitly test identifiers. Demo passwords appear only in generated fixtures and must be hashed by the importer.

## Reproduction and files

From the repository root, run:

```powershell
python scripts/generate_demo.py --seed 240917 --reference-date 2026-09-27
python scripts/generate_evals.py
python evals/run.py validate
```

Use the project's configured Python command if `python` is unavailable. `--seed`, `--reference-date`, `--output`, and `--small-output` are configurable. The default full fixture is `fixtures/demo_full.json`; a compact, referentially complete subset is `fixtures/demo_small.json`. The full fixture is generated locally and ignored by `fixtures/.gitignore`; the small fixture and generators are suitable for source control. The evaluation inputs and labels are separate files under `evals/`. Regenerate evaluation cases after changing the seed or reference date.

The default reference date is **2026-09-27 UTC**. All transaction timestamps use ISO 8601 UTC. The order sample spans the 12 calendar months **October 2025 through September 2026**. Prices and totals are integer USD cents. Version content is extracted-text-style Markdown, including headings, section IDs, and simulated page references; it is not a collection of original binary PDF files.

## Entity counts

| Entity | Northstar | Harbor | Total |
|---|---:|---:|---:|
| Workspaces | 1 | 1 | 2 |
| Products | 90 | 30 | 120 |
| Customers | 640 | 160 | 800 |
| Orders | 2,400 | 600 | 3,000 |
| Knowledge documents | 64 | 16 | 80 |
| Historical conversations | 320 | 80 | 400 |
| Review proposals | 32 | 8 | 40 |

There are 806 users: an admin, operator, and viewer in each workspace plus one synthetic customer login per customer. Orders contain line items, shipment timelines, and 189 recorded historical returns. The 80 documents cover ten categories: shipping, returns, warranty, care, assembly, compatibility, payments, accounts, troubleshooting, and product specifications. Fifty-five are model-specific owner manuals. The remaining documents are dated policies, support guides, and a general FAQ. Current policies and selected historical versions differ in return windows, late-delivery thresholds, and warranty terms.

## Distributions and planted cases

- Order statuses: 2,821 delivered, 44 in transit, 111 cancelled, and 24 processing. The number of items and purchase frequency vary; shipments may be late, undelivered, or already returned. Totals are recomputed from item quantity and unit price.
- Proposals: 9 pending review, 9 approved, 8 rejected, 7 expired, and 7 executed. Executed synthetic proposals have matching recorded return quantities.
- 113 customers lack an optional phone number. Display names repeat because the finite fictional name list is reused; customer IDs and emails remain unique. Some products have no owner manual, so retrieval must acknowledge missing evidence.
- The current Northstar returns FAQ broadly says 30 days for most items, while its authoritative policy sets a 21-day monitor window. Earlier dated versions used a 30-day monitor window. This tests source authority and effective-date selection rather than first-hit retrieval.
- The hero path is `cust_ns_demo_001` → `ord_ns_demo_001` → `line_ns_demo_001` → `conv_ns_demo_001` → `proposal_ns_demo_001`. The monitor order was promised on 2026-08-14 and delivered on 2026-08-26, 12 days late. On the reference date, the normal 21-day monitor window has closed, but the 45-day late-delivery exception is open and requires operator review. No refund or external message is sent.
- Harbor uses different return rules and isolated customers/orders. Cross-workspace case inputs deliberately quote foreign order numbers; server-bound identity must still deny access.

## Shape and relationships

The JSON top level has `metadata`, `workspaces`, `users`, `customers`, `products`, `orders`, `documents`, `conversations`, and `proposals`. Every record has a stable fictional ID and `workspace_id` where relevant. Users include `customer_id` or null, `email`, `name`, `role`, and a **demo-only** plain password. Products include SKU, category, price, and category-specific specifications. Orders include customer, number, total, line items with returned quantity, shipments, and return records. Documents include kind, category, authority, status, current version, and versioned content with SHA-256, effective dates, publication timestamp, and sections. Conversations contain messages; proposals link to a customer, order line, and optionally a conversation.

The generator validates record counts, unique IDs, workspace-scoped references, line totals, return quantities, shipment order, document hashes, and 12-month coverage. `evals/run.py validate` repeats fixture integrity checks and verifies evaluation quotas and label separation. Generation is deterministic for a fixed seed and reference date.

## Evaluation separation and limits

`evals/cases.jsonl` holds case inputs. `evals/ground_truth.jsonl` holds derived expected actions, structured claims, source IDs, and forbidden disclosures. **Do not index or expose the ground-truth file to the runtime app or model prompt.** Development and held-out product questions use disjoint product/manual entities. Policy topics necessarily share the small policy collection, but held-out prompts use different wording and policy-date tests require the correct historical version. The split tests this synthetic scenario only; it cannot establish real-customer answer quality or connector reliability.

The dataset is intentionally compact and programmatically generated. Names, product families, transaction mix, document wording, and exceptions are plausible but do not reproduce the complexity of a real catalog, carrier feed, or legal policy. Page numbers are synthetic extraction references. Report any model quality result with its exact case split and human review method; do not generalize it to live customers.
