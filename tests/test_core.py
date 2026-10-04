import hashlib
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import ValidationError

from rag_lab.core.accounting import break_even, embedding_cost, fact_coverage, generation_cost
from rag_lab.core.chunking import Chunk, chunk_document, pack_context, tokens
from rag_lab.core.config import Settings
from rag_lab.core.errors import AppError
from rag_lab.core.models import ChunkSettings, Page, ParsedDocument, Prices, Question, Usage
from rag_lab.core.providers import Provider
from rag_lab.core.security import require_editor, resolve_identity


@pytest.mark.parametrize(
    "index,baseline,rag,expected",
    [
        ("1", ".2", ".1", 11),
        ("1", ".2", ".2", None),
        ("0", ".2", ".1", 1),
        ("1.01", ".2", ".1", 11),
        ("1", ".1", ".2", None),
    ],
)
def test_break_even_is_strictly_cheaper(index, baseline, rag, expected):
    assert break_even(Decimal(index), Decimal(baseline), Decimal(rag)) == expected


def test_money_and_negative_savings():
    usage = Usage(input_tokens=1000000, output_tokens=500000, source="synthetic")
    assert generation_cost(usage, Prices()) == Decimal("1.20")
    assert embedding_cost(1000000, Prices()) == Decimal("0.02")
    assert Decimal(".001") - Decimal(".002") < 0


@pytest.mark.parametrize(
    "payload",
    [
        {"top_k": 0},
        {"tenant_id": str(uuid4())},
        {"expected_facts": [""]},
        {"prices": {"input_per_million": "NaN"}},
    ],
)
def test_invalid_inputs(payload):
    with pytest.raises(ValidationError):
        Question(question="What is in the document?", **payload)


def test_coverage_is_not_correctness():
    assert fact_coverage("Nothing", []) is None
    assert fact_coverage("GOVERN and MAP", ["govern", "map", "measure", "manage"]) == 0.5


def test_chunk_budget_provenance_and_reproducibility():
    parsed = ParsedDocument(
        pages=[
            Page(number=1, text="A relevant sentence. " * 350),
            Page(number=2, text="Another section. " * 200),
        ]
    )
    config = ChunkSettings(size=100, overlap=10, parent_size=500)
    first, second = chunk_document(parsed, config), chunk_document(parsed, config)
    assert [c.key for c in first] == [c.key for c in second]
    assert all(tokens(c.text) <= 100 for c in first)
    assert {c.page for c in first} == {1, 2}
    text, selected = pack_context(first, "parent_child", 1000)
    assert tokens(text) <= 1000
    assert len({c.parent_key for c in selected}) == len(selected)


def test_oversized_parent_is_skipped_not_silently_truncated():
    chunk = Chunk("x", 1, "small", "p", "long text " * 2000)
    assert pack_context([chunk], "parent_child", 100) == ("", [])


def test_cipher_is_tenant_and_object_bound(cipher, tenant):
    ciphertext = cipher.encrypt(tenant, b"confidential text", "object-a")
    assert b"confidential text" not in ciphertext
    assert cipher.decrypt(tenant, ciphertext, "object-a") == b"confidential text"
    with pytest.raises(InvalidTag):
        cipher.decrypt(uuid4(), ciphertext, "object-a")
    with pytest.raises(InvalidTag):
        cipher.decrypt(tenant, ciphertext, "object-b")


def test_tenant_resolved_from_credential_registry(tenant):
    key = "a" * 40
    registry = json.dumps(
        {
            hashlib.sha256(key.encode()).hexdigest(): {
                "tenant_id": str(tenant),
                "user_id": "alice",
                "role": "reader",
            }
        }
    )
    user = resolve_identity(key, registry)
    assert user.tenant_id == tenant
    with pytest.raises(AppError) as exc:
        require_editor(user)
    assert exc.value.status == 403
    with pytest.raises(AppError):
        resolve_identity("b" * 40, registry)


def test_demo_provider_is_explicit_and_local():
    provider = Provider(Settings(provider_mode="demo", _env_file=None))
    assert len(provider.embed("governance")) == 768
    result = provider.answer("How long?", "[Page 1] The retention period is 30 days.")
    assert result.usage.source == "synthetic"
    assert "30 days" in result.text


@pytest.mark.parametrize(
    "url", ["https://example.com", "http://169.254.169.254", "http://user@localhost"]
)
def test_external_endpoints_rejected(url):
    with pytest.raises(ValidationError):
        Settings(ollama_url=url, _env_file=None)
