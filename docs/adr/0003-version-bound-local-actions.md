# ADR 0003: Version-bound review and local action ledger

**Status:** Accepted for local return actions.

A proposal stores a hash of the exact requested action and policy result. LangGraph interrupts before review; an operator decision carries that version. The side-effect step rechecks role, workspace, proposal state, expiration, and available quantity. A unique return record and action-ledger key make a repeated local approval return the existing record. This adds explicit state and storage, but makes restarts and repeated clicks observable. Third-party writes may still time out after succeeding; their adapters must reconcile by external ID before retrying rather than claiming universal exactly-once delivery.
