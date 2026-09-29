# ADR 0002: SQLite demo, PostgreSQL target

**Status:** Accepted provisionally; PostgreSQL path unverified here.

The default local demonstration uses SQLite and a file-backed LangGraph checkpoint saver to avoid requiring a database server for a walkthrough. Alembic migrations and retrieval code include PostgreSQL/pgvector, which is the intended installed deployment store. Document bytes live in a scoped upload directory, not graph state. The tradeoff is two database dialect paths, and SQLite cannot establish PostgreSQL concurrency or vector-search performance. A customer deployment requires PostgreSQL migration, checkpoint initialization, backup/restore, and concurrency tests.
