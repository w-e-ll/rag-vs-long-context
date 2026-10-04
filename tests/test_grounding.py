import json

import pytest

from rag_lab.core.grounding import check_evidence, decode_output
from rag_lab.core.models import Answer, Usage


def answer(source="S006", quote="GOVERN, MAP, MEASURE, and MANAGE"):
    raw = json.dumps(
        dict(
            status="answered",
            claims=[
                dict(
                    text="Four core functions",
                    source=source,
                    quote=quote,
                )
            ],
        )
    )
    return Answer(
        **decode_output(raw),
        usage=Usage(input_tokens=30, output_tokens=40, source="model_reported"),
        latency_ms=10,
    )


def test_quote_whitespace_and_raw_output_preserved():
    result = answer()
    raw = result.raw_model_output
    check_evidence(result, {"S006": ["Functions: GOVERN, MAP, MEASURE,\nand MANAGE."]})
    assert result.citation_check == "quote_match_only"
    assert result.raw_model_output == raw
    assert result.usage.output_tokens == 40


@pytest.mark.parametrize(
    "sources",
    [
        {"S003": ["GOVERN, MAP, MEASURE, and MANAGE"]},
        {"S006": ["unrelated evidence"]},
        {"S006": ["GOVERN, MAP,", "MEASURE, and MANAGE"]},
    ],
)
def test_wrong_source_absent_quote_and_cross_fragment_quote_fail(sources):
    result = answer()
    check_evidence(result, sources)
    assert result.citation_check == "evidence_invalid"
    assert result.citation_warnings


@pytest.mark.parametrize(
    "raw",
    [
        '{"status":"answered","claims":[]}',
        '{"status":"insufficient_evidence","claims":[],"text":"Price is $20"}',
        '{"status":',
    ],
)
def test_malformed_results_remain_inspectable(raw):
    result = decode_output(raw)
    assert result["citation_check"] == "structured_invalid"
    assert result["raw_model_output"] == raw


def test_abstention_does_not_claim_verified_absence():
    result = decode_output('{"status":"insufficient_evidence","claims":[]}')
    assert result["citation_check"] == "abstention_unverified"


@pytest.mark.parametrize("quote", ["", "   ", "short"])
def test_missing_or_short_quote_keeps_answer_visible_but_fails_evidence(quote):
    result = answer(quote=quote)
    assert result.text == "Four core functions [S006]"
    assert result.raw_model_output is not None
    check_evidence(result, {"S006": ["GOVERN, MAP, MEASURE, and MANAGE"]})
    assert result.citation_check == "evidence_invalid"
    assert "missing or too short" in result.citation_warnings[0]


def test_empty_quote_never_matches_every_fragment():
    result = answer(quote="")
    check_evidence(result, {"S006": ["Any supplied evidence"]})
    assert result.citation_check == "evidence_invalid"


def test_empty_quote_gets_transparent_source_excerpt():
    result = answer(quote="")
    check_evidence(
        result,
        {"S006": ["The four AI RMF Core functions are GOVERN, MAP, MEASURE, and MANAGE."]},
    )
    assert result.citation_check == "quote_match_only"
    assert result.evidence_derivation == "source_excerpt"
    assert result.evidence_claims[0].quote.startswith("The four AI RMF Core functions")
