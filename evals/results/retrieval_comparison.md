# Retrieval comparison

Database: SQLite lexical plus deterministic local vector approximation. 80 grounded questions.

| Strategy | Source in top 1 | Source in top 6 | Median / p95 ms |
|---|---:|---:|---:|
| baseline | 69/80 | 77/80 | 10.93 / 11.52 |
| hybrid | 80/80 | 80/80 | 12.08 / 12.83 |

PostgreSQL full-text plus pgvector performance remains unverified until a database is available.
