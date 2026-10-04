import base64
import hashlib
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from rag_lab.api.main import app, repository
from rag_lab.core.config import settings
from rag_lab.core.errors import AppError


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("rag_lab.api.main.throttle", lambda *_: None)
    token = "a" * 40
    tenant = uuid4()
    monkeypatch.setenv(
        "CREDENTIALS_JSON",
        json.dumps(
            {
                hashlib.sha256(token.encode()).hexdigest(): {
                    "tenant_id": str(tenant),
                    "user_id": "test",
                    "role": "reader",
                }
            }
        ),
    )
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(b"k" * 32).decode())
    settings.cache_clear()

    class Fake:
        def list_documents(self, t):
            assert t == tenant
            return []

        def document(self, t, doc_id):
            raise AppError("not_found", "Document not found", 404)

    app.dependency_overrides[repository] = lambda: Fake()
    with TestClient(app) as c:
        yield c, {"Authorization": "Bearer " + token}
    app.dependency_overrides.clear()
    settings.cache_clear()


def test_auth_required(client):
    c, headers = client
    assert c.get("/api/v1/documents").status_code == 401
    assert c.get("/api/v1/documents", headers=headers).json() == []


def test_unknown_and_cross_tenant_id_are_not_disclosed(client):
    c, headers = client
    response = c.get("/api/v1/documents/" + str(uuid4()), headers=headers)
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]


def test_reader_cannot_upload(client):
    c, headers = client
    response = c.post(
        "/api/v1/documents",
        headers={**headers, "Idempotency-Key": str(uuid4()), "Content-Type": "application/pdf"},
        content=b"%PDF-test",
    )
    assert response.status_code == 403


def test_validation_does_not_echo_confidential_payload(client):
    c, headers = client
    response = c.post(
        "/api/v1/documents/" + str(uuid4()) + "/compare",
        headers=headers,
        json={"question": "SECRET", "tenant_id": "TENANT-SECRET"},
    )
    assert response.status_code == 422
    assert "SECRET" not in response.text


def test_body_limit_rejects_before_parsing(client):
    c, headers = client
    response = c.post(
        "/api/v1/documents/" + str(uuid4()) + "/review", headers=headers, content=b"x" * 4000001
    )
    assert response.status_code == 413
