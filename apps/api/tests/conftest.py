from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["APP_MODE"] = "DEMO"
os.environ["DATABASE_URL"] = "sqlite:///./data/test_suite.db"
os.environ["UPLOAD_ROOT"] = "./data/test_uploads"

from supportpilot.api import app  # noqa: E402
from supportpilot.seed import ROOT, migrate, seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    Path("data").mkdir(exist_ok=True)
    migrate()
    seed(ROOT / "fixtures" / "demo_small.json", reset=True)


@pytest.fixture
def client(seeded_database):
    with TestClient(app) as instance:
        yield instance


def login(client: TestClient, email: str) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": "DemoPass!2026"})
    assert response.status_code == 200, response.text
