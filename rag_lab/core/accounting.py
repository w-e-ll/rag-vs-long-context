"""Scenario estimates, not invoices. Negative savings remain visible."""

from decimal import ROUND_CEILING, Decimal

from rag_lab.core.models import Prices, Usage


def generation_cost(usage: Usage, prices: Prices) -> Decimal:
    return (
        usage.input_tokens * prices.input_per_million
        + usage.output_tokens * prices.output_per_million
    ) / Decimal(1000000)


def embedding_cost(tokens: int, prices: Prices) -> Decimal:
    return tokens * prices.embedding_per_million / Decimal(1000000)


def break_even(indexing: Decimal, baseline: Decimal, rag: Decimal) -> int | None:
    difference = baseline - rag
    if difference <= 0:
        return None
    # Strictly cheaper: equality is not savings.
    ratio = indexing / difference
    return max(
        1,
        int(ratio.to_integral_value(rounding=ROUND_CEILING))
        + (1 if ratio == ratio.to_integral_value() else 0),
    )


def fact_coverage(answer: str, expected: list[str]) -> float | None:
    if not expected:
        return None
    normalized = " ".join(answer.casefold().split())
    return sum(" ".join(f.casefold().split()) in normalized for f in expected) / len(expected)
