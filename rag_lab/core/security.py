"""Server-owned tenant resolution and authenticated encryption for text artifacts."""

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from rag_lab.core.errors import AppError


@dataclass(frozen=True)
class Identity:
    tenant_id: UUID
    user_id: str
    role: str


def credential_record(record, *, require_expiry=False):
    """Validate operator records; reject malformed/expired/disabled credentials safely."""
    if not isinstance(record, dict):
        raise ValueError("Invalid credential record")
    if record.get("role") not in {"reader", "editor", "admin"}:
        raise ValueError("Invalid credential role")
    if not isinstance(record.get("user_id"), str) or not 1 <= len(record["user_id"]) <= 200:
        raise ValueError("Invalid credential user")
    tenant = UUID(record["tenant_id"])
    disabled = record.get("disabled", False)
    if not isinstance(disabled, bool):
        raise ValueError("Invalid credential state")
    expiry = record.get("expires_at")
    if expiry is None and require_expiry:
        raise ValueError("Production credentials require expiry")
    if expiry is not None:
        if not isinstance(expiry, str):
            raise ValueError("Invalid credential expiry")
        expiry = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            raise ValueError("Credential expiry requires timezone")
    if disabled or (expiry is not None and expiry <= datetime.now(timezone.utc)):
        return None
    return Identity(tenant, record["user_id"], record["role"])


def resolve_identity(token: str, registry: str) -> Identity:
    """Only credential hashes live in the registry. There is no client tenant selector."""
    if not 32 <= len(token) <= 256:
        raise AppError("unauthorized", "A valid access token is required", 401)
    digest = hashlib.sha256(token.encode()).hexdigest()
    for key_hash, record in json.loads(registry).items():
        if hmac.compare_digest(digest, key_hash):
            try:
                identity = credential_record(record)
            except (ValueError, TypeError, KeyError, AttributeError):
                identity = None
            if identity is not None:
                return identity
            break
    raise AppError("unauthorized", "A valid access token is required", 401)


def require_editor(identity: Identity):
    if identity.role not in {"editor", "admin"}:
        raise AppError("forbidden", "An editor role is required", 403)


class Cipher:
    def __init__(self, encoded_key: str):
        try:
            self.key = base64.b64decode(encoded_key, validate=True)
            if len(self.key) != 32:
                raise ValueError()
        except ValueError as exc:
            raise AppError("key_missing", "Configure the encryption key", 503) from exc

    def _cipher(self, tenant: UUID):
        key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=tenant.bytes, info=b"rag-lab-v1"
        ).derive(self.key)
        return AESGCM(key)

    def encrypt(self, tenant: UUID, data: bytes, purpose: str) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._cipher(tenant).encrypt(nonce, data, purpose.encode())

    def decrypt(self, tenant: UUID, data: bytes, purpose: str) -> bytes:
        return self._cipher(tenant).decrypt(data[:12], data[12:], purpose.encode())
