import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# TEST_DATABASE_URL lets the suite run against PostgreSQL too (it is wiped on every test).
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{ROOT / 'test.db'}"
os.environ["RUN_WORKER"] = "false"
os.environ["ENV"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import seed  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    seed.main()
    with TestClient(app) as c:
        yield c


def login(client, phone: str) -> dict:
    r = client.post("/v1/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    r = client.post("/v1/auth/otp/verify", json={"phone": phone, "code": r.json()["dev_code"]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def idem() -> dict:
    return {"Idempotency-Key": uuid.uuid4().hex}
