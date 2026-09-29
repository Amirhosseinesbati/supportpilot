# ADR 0001: One API with capability modules

**Status:** Accepted for the pilot.

FastAPI owns authentication, workspace checks, chat, knowledge, returns, and tickets in one deployable service. Domain rules such as return eligibility remain plain Python functions; adapters isolate external commerce, support, and model calls. This keeps local installation and transaction boundaries simple while allowing customer-specific connectors. The cost is that background work currently shares the API process; a separate durable worker deployment would be needed for higher availability.
