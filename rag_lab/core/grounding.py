"""Validate model evidence against trusted context fragments, not model-generated markers."""

import re

from pydantic import ValidationError

from rag_lab.core.citations import ABSTENTION
from rag_lab.core.models import GroundedOutput


def _source_excerpt(claim_text: str, fragments: list[str]) -> str | None:
    """Find an exact, useful source sentence when the model omitted its quote."""
    wanted = {
        token.casefold() for token in re.findall(r"[A-Za-z0-9]+", claim_text) if len(token) > 2
    }
    if len(wanted) < 2:
        return None
    best = None
    for fragment in fragments:
        for sentence in re.split(r"(?<=[.!?])\s+", fragment):
            normalized = " ".join(sentence.split())
            if len(normalized) < 10:
                continue
            tokens = {token.casefold() for token in re.findall(r"[A-Za-z0-9]+", normalized)}
            overlap = len(wanted & tokens)
            candidate = (overlap, -len(normalized), normalized)
            if best is None or candidate > best:
                best = candidate
    if best is None or best[0] < 2:
        return None
    return best[2][:3000]


def decode_output(raw: str) -> dict:
    try:
        result = GroundedOutput.model_validate_json(raw)
    except (ValidationError, ValueError):
        return dict(
            text="Model output could not be validated. Inspect the saved raw response.",
            raw_model_output=raw,
            citation_check="structured_invalid",
            citation_warnings=["Invalid structured response; answer is not verified."],
        )
    return dict(
        text=ABSTENTION
        if result.status == "insufficient_evidence"
        else "\n".join(f"{claim.text} [{claim.source}]" for claim in result.claims),
        raw_model_output=raw,
        evidence_claims=result.claims,
        citation_check=(
            "abstention_unverified"
            if result.status == "insufficient_evidence"
            else "structured_pending"
        ),
    )


def check_evidence(answer, sources: dict[str, list[str]]):
    if answer.citation_check != "structured_pending":
        return
    warnings = []
    derived = False
    for number, claim in enumerate(answer.evidence_claims, 1):
        fragments = sources.get(claim.source)
        if fragments is None:
            warnings.append(f"Claim {number}: unknown source {claim.source}.")
            continue
        normalized_quote = " ".join(claim.quote.split())
        if len(normalized_quote) < 10:
            excerpt = _source_excerpt(claim.text, fragments)
            if excerpt is not None:
                claim.quote = excerpt
                derived = True
                continue
            warnings.append(
                f"Claim {number}: supporting quote is missing or too short for {claim.source}."
            )
            continue
        if not any(normalized_quote in " ".join(fragment.split()) for fragment in fragments):
            warnings.append(f"Claim {number}: quote not found in supplied source {claim.source}.")
    answer.citation_warnings = warnings
    answer.evidence_derivation = "source_excerpt" if derived else "none"
    answer.citation_check = "evidence_invalid" if warnings else "quote_match_only"
