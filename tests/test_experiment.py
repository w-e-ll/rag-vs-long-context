from uuid import uuid4

import pytest

from rag_lab.core.chunking import Chunk
from rag_lab.core.config import Settings
from rag_lab.core.experiment import compare
from rag_lab.core.models import ChunkSettings, Page, ParsedDocument, Question
from rag_lab.core.providers import Provider


def test_paired_experiment_preserves_signed_costs_and_source():
    doc_id, run_id = uuid4(), uuid4()
    provider = Provider(Settings(provider_mode="demo", _env_file=None))
    question = Question(
        run_id=run_id,
        question="How long is retention?",
        expected_facts=["30 days"],
        projected_questions=10,
    )
    parsed = ParsedDocument(pages=[Page(number=1, text="Retention is 30 days.")])

    class Repo:
        def unseal(self, tenant, value, purpose):
            return value

        def document(self, tenant, selected):
            assert selected == doc_id
            return {
                "id": doc_id,
                "status": "ready",
                "embedding_fingerprint": provider.fingerprint,
                "parsed": parsed.model_dump(),
                "config": ChunkSettings().model_dump(),
                "indexing_tokens": 100000,
                "indexing_ms": 3.0,
                "digest": "a" * 64,
            }

        def retrieve(self, tenant, selected, vector, k):
            assert selected == doc_id
            return [Chunk("x", 1, "Retention is 30 days.", "p1", "Retention is 30 days.")]

    result = compare(
        Repo(),
        uuid4(),
        {"id": run_id, "document_id": doc_id, "payload": question.model_dump(mode="json")},
        provider,
    )
    assert result.first_question_savings < 0
    assert result.retrieved_pages == [1]
    assert result.long_context.fact_coverage == 1
    assert result.rag.fact_coverage == 1
    assert result.document_sha256 == "a" * 64
    assert len(result.parsed_sha256) == 64
    assert result.rag_end_to_end_ms >= result.rag.latency_ms
    assert result.provider == "demo"


def test_incomplete_provider_usage_never_becomes_zero():
    from pydantic import ValidationError

    from rag_lab.core.models import Answer

    with pytest.raises(ValidationError):
        Answer(text="Result", latency_ms=1, usage={})
