"""Paired comparison with identical parsed source, model, question and price snapshot."""

import hashlib
import time

from rag_lab.core.accounting import break_even, embedding_cost, fact_coverage, generation_cost
from rag_lab.core.chunking import pack_context, tokens
from rag_lab.core.citations import citation_warnings, is_abstention, source_id, source_text
from rag_lab.core.errors import AppError
from rag_lab.core.grounding import check_evidence
from rag_lab.core.metrics import STAGE_TIME
from rag_lab.core.models import ChunkSettings, Comparison, ParsedDocument, Question


def compare(repo, tenant, job, provider):
    request = Question.model_validate(repo.unseal(tenant, job["payload"], str(job["id"])))
    doc = repo.document(tenant, job["document_id"])
    if doc["status"] != "ready" or doc["embedding_fingerprint"] != provider.fingerprint:
        raise AppError("index_changed", "Document index is unavailable or its model changed", 409)
    parsed = ParsedDocument.model_validate(repo.unseal(tenant, doc["parsed"], str(doc["id"])))
    config = ChunkSettings.model_validate(doc["config"])
    full_context = "\n\n".join(
        f"[{source_id(p.number)}]\n{source_text(p.text)}\n[END SOURCE]" for p in parsed.pages
    )
    if tokens(full_context) + tokens(request.question) > provider.config.max_document_tokens:
        raise AppError("context_limit", "Document exceeds the long-context experiment limit")
    start = time.perf_counter()
    with STAGE_TIME.labels("query_embedding").time():
        vector = provider.embed(request.question)
    with STAGE_TIME.labels("retrieval").time():
        retrieved = repo.retrieve(tenant, doc["id"], vector, request.top_k)
        context, selected = pack_context(retrieved, config.strategy, request.context_budget)
    retrieval_ms = (time.perf_counter() - start) * 1000
    if not context:
        raise AppError("empty_retrieval", "No complete evidence block fits the context budget")
    order = ["long_context", "rag"] if job["id"].int % 2 else ["rag", "long_context"]
    answers = {}
    for mode in order:
        with STAGE_TIME.labels(mode).time():
            answer = provider.answer(
                request.question, full_context if mode == "long_context" else context
            )
        answer.estimated_cost = generation_cost(answer.usage, request.prices)
        answer.fact_coverage = fact_coverage(answer.text, request.expected_facts)
        if provider.config.provider_mode == "ollama":
            allowed = (
                {p.number for p in parsed.pages}
                if mode == "long_context"
                else {c.page for c in selected}
            )
            sources = {}
            if mode == "long_context":
                sources = {source_id(p.number): [source_text(p.text)] for p in parsed.pages}
            else:
                for chunk in selected:
                    fragment = (
                        chunk.parent_text if config.strategy == "parent_child" else chunk.text
                    )
                    sources.setdefault(source_id(chunk.page), []).append(source_text(fragment))
            check_evidence(answer, sources)
            if answer.citation_check == "not_checked":
                answer.citation_warnings = citation_warnings(answer.text, allowed)
                answer.citation_check = (
                    "abstention_unverified"
                    if is_abstention(answer.text)
                    else "source_membership_only"
                )
            # A lexical fact score must not look like verified coverage when
            # the model's supporting evidence failed validation.
            if answer.citation_check == "evidence_invalid":
                answer.fact_coverage = None
            answer.citation_sources = {source_id(p): p for p in sorted(allowed)}
        answers[mode] = answer
    baseline, rag = answers["long_context"], answers["rag"]
    index_cost = embedding_cost(doc["indexing_tokens"], request.prices)
    query_tokens = tokens(request.question)
    rag_cost = rag.estimated_cost + embedding_cost(query_tokens, request.prices)
    return Comparison(
        run_id=job["id"],
        document_id=doc["id"],
        document_sha256=doc["digest"],
        parsed_sha256=hashlib.sha256(parsed.model_dump_json().encode()).hexdigest(),
        parser_version=parsed.parser_version,
        provider=provider.config.provider_mode,
        llm_model=provider.config.llm_model
        if provider.config.provider_mode != "demo"
        else "lexical-demo",
        embedding_model=provider.fingerprint,
        order=order,
        settings=config,
        request=request,
        long_context=baseline,
        rag=rag,
        retrieved_pages=sorted({c.page for c in selected}),
        retrieved_chunks=[c.key for c in selected],
        context_tokens=tokens(context),
        indexing_tokens=doc["indexing_tokens"],
        query_embedding_tokens=query_tokens,
        indexing_ms=doc["indexing_ms"],
        retrieval_ms=retrieval_ms,
        rag_end_to_end_ms=retrieval_ms + rag.latency_ms,
        indexing_cost=index_cost,
        rag_per_query_cost=rag_cost,
        first_question_savings=baseline.estimated_cost - rag_cost - index_cost,
        projected_savings=(baseline.estimated_cost - rag_cost) * request.projected_questions
        - index_cost,
        break_even_questions=break_even(index_cost, baseline.estimated_cost, rag_cost),
        limitations=[
            "USD is an illustrative token-price scenario, not a local-model bill.",
            "Parsing/review is shared. Hosting, OCR compute, electricity and labour are excluded.",
            "Embedding tokens and context budgets use cl100k_base estimates, not model usage.",
            "Fact coverage is literal reference-fact matching, not proof of correctness.",
            "Single paired sample; repeat with both execution orders before latency conclusions.",
            "Both modes use reviewed extracted text; neither receives the original visual PDF.",
            "No automatic claim of optimal settings or guaranteed savings.",
        ],
    )
