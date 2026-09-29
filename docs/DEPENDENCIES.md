# Dependency and runtime record

The backend manifest is `apps/api/pyproject.toml` with a committed `uv.lock`; the frontend uses `apps/web/package.json` and `pnpm-lock.yaml`. The versions below are the **resolved lock versions inspected on 2026-09-27**, not a claim that every deployment combination or external connector has been exercised. The local tool bundle reports Python 3.12.13 and Node.js 24.19.0; the package declares pnpm 11.19.0. The root Compose file pins `pgvector/pgvector:0.8.6-pg17-bookworm`; `docker compose config --quiet` passed, but a Docker daemon was not available for image or database verification here.

| Capability | Locked version |
|---|---:|
| FastAPI | 0.141.1 |
| Uvicorn | 0.54.0 |
| SQLAlchemy | 2.1.1 |
| Alembic | 1.20.0 |
| Pydantic settings | 2.15.0 |
| psycopg | 3.3.6 |
| pgvector Python package | 0.5.0 |
| LangChain / LangChain Core | 1.4.2 / 1.6.5 |
| LangGraph | 1.2.12 |
| LangGraph PostgreSQL / SQLite checkpoints | 3.1.2 / 3.1.1 |
| LangChain OpenAI adapter | 1.6.6 |
| pypdf | 6.19.0 |
| Argon2 CFFI | 25.1.0 |
| React / React DOM | 19.3.0 |
| Vite | 8.3.1 |
| TypeScript | 5.9.3 |
| Tailwind CSS | 4.3.3 |
| TanStack Query | 5.104.0 |
| Lucide React | 1.48.0 |

For reproducible installation, run `uv sync --locked` from `apps/api` and `pnpm install --frozen-lockfile` from `apps/web`. The Windows DEMO preparation installed from these locks and passed; the POSIX launcher has passed a Bash syntax check only. The current source uses `StateGraph`, interrupts, LangGraph checkpoint savers, LangChain documents/text splitting, and `ChatOpenAI.with_structured_output`; do not substitute older tutorial imports. Official compatibility references are linked from the product requirements and should be rechecked before upgrading a lockfile. The PostgreSQL image, pgvector extension, checkpoint schema, and connected model call require separate integration tests.

The frontend includes package icons from Lucide and no downloaded commercial imagery. Before redistribution to a buyer, perform a license/SBOM review of the exact lockfiles, container image, fonts/assets, and every customer-provided document; this review has not been recorded as complete.
