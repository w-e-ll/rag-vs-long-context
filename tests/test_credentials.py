import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from rag_lab.core.config import Settings
from rag_lab.core.errors import AppError
from rag_lab.core.security import resolve_identity


def registry(**updates):
    record = dict(
        tenant_id=str(uuid4()),
        user_id="editor",
        role="editor",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    record.update(updates)
    return json.dumps({hashlib.sha256(b"t" * 40).hexdigest(): record})


@pytest.mark.parametrize(
    "updates",
    [
        {"expires_at": "2000-01-01T00:00:00Z"},
        {"disabled": True},
        {"expires_at": "2099-01-01"},
        {"expires_at": "PRIVATE_BAD_EXPIRY"},
        {"tenant_id": "PRIVATE_BAD_TENANT"},
        {"disabled": "false"},
    ],
)
def test_expired_disabled_or_malformed_credential_is_denied(updates):
    with pytest.raises(AppError) as exc:
        resolve_identity("t" * 40, registry(**updates))
    assert exc.value.status == 401
    assert "PRIVATE" not in exc.value.message


def test_active_expiring_credential_resolves():
    assert resolve_identity("t" * 40, registry()).user_id == "editor"


def production(**updates):
    config = dict(
        deployment_mode="production",
        provider_mode="ollama",
        encryption_key=base64.b64encode(b"k" * 32).decode(),
        credentials_json=registry(),
        _env_file=None,
    )
    config.update(updates)
    return Settings(**config)


def test_production_guards():
    assert production().deployment_mode == "production"
    for changes in (
        {"provider_mode": "demo"},
        {"encryption_key": "SECRET_BAD_KEY"},
        {"credentials_json": registry(expires_at=None)},
        {"credentials_json": registry(disabled=True)},
    ):
        with pytest.raises(ValidationError) as exc:
            production(**changes)
        assert "SECRET_BAD_KEY" not in str(exc.value)
