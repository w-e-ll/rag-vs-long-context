"""Strict contracts shared by the API, queue and experiment engine."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceBlock(Model):
    kind: Literal["table", "image_text", "visual_description"]
    source: Literal["pdf_geometry", "tesseract", "local_vision"]
    text: str = Field(default="", max_length=20000)
    bbox: list[float] = Field(default_factory=list, max_length=4)
    rows: list[list[str]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def bounded_cells(self):
        if any(len(row) > 20 or any(len(cell) > 8000 for cell in row) for row in self.rows):
            raise ValueError("Table exceeds extraction limits")
        if sum(len(cell) for row in self.rows for cell in row) > 40000:
            raise ValueError("Table text exceeds extraction limits")
        return self


class Page(Model):
    number: int = Field(ge=1, le=100)
    text: str = Field(max_length=40000)
    method: Literal["text", "ocr", "hybrid", "manual"] = "text"
    warnings: list[str] = Field(default_factory=list, max_length=20)
    blocks: list[EvidenceBlock] = Field(default_factory=list, max_length=40)
    ocr_confidence: float | None = Field(default=None, ge=0, le=100)
    vision_status: Literal["disabled", "not_needed", "completed", "failed", "budget_exceeded"] = (
        "disabled"
    )
    vision_model: str | None = None
    extraction_ms: float = Field(default=0, ge=0)
    vision_ms: float = Field(default=0, ge=0)
    vision_input_tokens: int = Field(default=0, ge=0)
    vision_output_tokens: int = Field(default=0, ge=0)


class ParsedDocument(Model):
    pages: list[Page] = Field(min_length=1, max_length=100)
    parser_version: str = "pdf-v1"

    @model_validator(mode="after")
    def unique_pages(self):
        if [p.number for p in self.pages] != list(range(1, len(self.pages) + 1)):
            raise ValueError("Pages must be ordered and consecutive")
        if sum(len(p.text) for p in self.pages) > 500000:
            raise ValueError("Extracted text exceeds the experiment limit")
        if sum(len(p.model_dump_json()) for p in self.pages) > 1000000:
            raise ValueError("Extracted evidence exceeds the experiment limit")
        return self


class ChunkSettings(Model):
    strategy: Literal["recursive", "parent_child"] = "recursive"
    size: int = Field(default=450, ge=100, le=1000)
    overlap: int = Field(default=60, ge=0, le=200)
    parent_size: int = Field(default=1400, ge=500, le=2400)

    @model_validator(mode="after")
    def valid_sizes(self):
        if self.overlap >= self.size or self.parent_size < self.size:
            raise ValueError("Overlap must be smaller than child; parent must fit child")
        return self


class Prices(Model):
    input_per_million: Money = Decimal("0.40")
    output_per_million: Money = Decimal("1.60")
    embedding_per_million: Money = Decimal("0.02")
    label: str = Field(default="Illustrative rates, not a provider quote", max_length=150)


class Review(Model):
    parsed: ParsedDocument
    settings: ChunkSettings = Field(default_factory=ChunkSettings)


class Question(Model):
    run_id: UUID = Field(default_factory=uuid4)
    question: str = Field(min_length=3, max_length=2000)
    expected_facts: list[str] = Field(default_factory=list, max_length=20)
    top_k: int = Field(default=4, ge=1, le=12)
    context_budget: int = Field(default=4000, ge=500, le=12000)
    projected_questions: int = Field(default=100, ge=1, le=1000000)
    prices: Prices = Field(default_factory=Prices)

    @model_validator(mode="after")
    def bounded_facts(self):
        if any(not f.strip() or len(f) > 500 for f in self.expected_facts):
            raise ValueError("Reference facts must contain 1-500 characters")
        return self


class Usage(Model):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    source: Literal["synthetic", "model_reported"]


class EvidenceClaim(Model):
    text: str = Field(min_length=1, max_length=2000)
    source: str = Field(pattern=r"^S\d{3,}$")
    # Evidence quality is checked after trusted source fragments are available.
    quote: str = Field(max_length=3000)


class GroundedOutput(Model):
    status: Literal["answered", "insufficient_evidence"]
    claims: list[EvidenceClaim] = Field(max_length=12)

    @model_validator(mode="after")
    def consistent_status(self):
        if (self.status == "answered") != bool(self.claims):
            raise ValueError("Answered requires claims; abstention requires an empty list")
        return self


class Answer(Model):
    text: str = Field(min_length=1, max_length=16000)
    usage: Usage
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    estimated_cost: Money = Decimal(0)
    fact_coverage: float | None = Field(default=None, ge=0, le=1)
    citation_warnings: list[str] = Field(default_factory=list)
    citation_check: Literal[
        "not_checked",
        "page_membership_only",
        "source_membership_only",
        "abstention_unverified",
        "quote_match_only",
        "evidence_invalid",
        "structured_pending",
        "structured_invalid",
    ] = "not_checked"
    citation_sources: dict[str, int] = Field(default_factory=dict)
    evidence_claims: list[EvidenceClaim] = Field(default_factory=list)
    evidence_derivation: Literal["none", "source_excerpt"] = "none"
    raw_model_output: str | None = None


class Comparison(Model):
    run_id: UUID
    document_id: UUID
    document_sha256: str
    parsed_sha256: str
    parser_version: str
    provider: str
    llm_model: str
    embedding_model: str
    order: list[Literal["long_context", "rag"]]
    settings: ChunkSettings
    request: Question
    long_context: Answer
    rag: Answer
    retrieved_pages: list[int]
    retrieved_chunks: list[str]
    context_tokens: int = Field(ge=0)
    indexing_tokens: int = Field(ge=0)
    query_embedding_tokens: int = Field(ge=0)
    indexing_ms: float = Field(ge=0, allow_inf_nan=False)
    retrieval_ms: float = Field(ge=0, allow_inf_nan=False)
    rag_end_to_end_ms: float = Field(ge=0, allow_inf_nan=False)
    indexing_cost: Money
    rag_per_query_cost: Money
    first_question_savings: Decimal
    projected_savings: Decimal
    break_even_questions: int | None = Field(default=None, ge=1)
    limitations: list[str]


class Resource(Model):
    id: UUID
    status: str


class DocumentView(Resource):
    parsed: ParsedDocument | None = None
    settings: ChunkSettings | None = None
    indexing_tokens: int = 0
    error_code: str | None = None


class JobView(Resource):
    kind: str
    document_id: UUID
    attempts: int
    error_code: str | None = None


class ErrorBody(Model):
    code: str
    message: str
    request_id: str
