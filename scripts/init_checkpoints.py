"""Create LangGraph's PostgreSQL checkpoint tables before serving requests."""

from supportpilot.config import settings
from supportpilot.graphs import checkpoint_saver


def main() -> None:
    if not settings.database_url.startswith("postgresql"):
        raise SystemExit("Checkpoint initialization expects a PostgreSQL DATABASE_URL")
    with checkpoint_saver() as saver:
        saver.setup()
    print("LangGraph PostgreSQL checkpoints initialized")


if __name__ == "__main__":
    main()
