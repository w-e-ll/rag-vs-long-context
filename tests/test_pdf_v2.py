import io
import json

import httpx
import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from rag_lab.core.models import EvidenceBlock
from rag_lab.ingestion.extract import parse_pdf
from rag_lab.ingestion.vision import analyze


def fixture_page(index):
    writer = PdfWriter()
    writer.add_page(PdfReader("examples/nist-mixed-fixture.pdf").pages[index])
    data = io.BytesIO()
    writer.write(data)
    return data.getvalue()


def test_nist_spacing_regression():
    parsed = parse_pdf(fixture_page(1))
    text = parsed.pages[0].text
    assert "also pose risks that can negatively impact" in text
    assert "can, for a given set of objectives, generate outputs" in text
    assert "in which they are deployed are frequently complex" in text
    assert "alsoposerisksthat" not in text
    assert parsed.parser_version == "pdf-v5"


def test_horizontal_only_table_preserves_categories_and_cells():
    page = parse_pdf(fixture_page(7)).pages[0]
    table = next(b for b in page.blocks if b.kind == "table")
    assert table.rows[0] == ["Categories", "Subcategories"]
    assert len(table.rows[2]) == 2
    assert "GOVERN 2:" in table.rows[2][0]
    assert "GOVERN 2.1:" in table.rows[2][1]
    assert "GOVERN 2.3:" in table.rows[2][1]
    assert "GOVERN 2.1:" not in table.rows[2][0]
    # Region text is replaced, not duplicated in row-interleaved prose.
    assert page.text.count("GOVERN 2.1:") == 1
    # A continued page must not invent the missing previous-page category.
    assert table.rows[1][0] == ""


def test_mixed_page_ocr_runs_even_with_a_readable_text_layer(monkeypatch):
    seen = []

    def ocr(image):
        seen.append(image.size)
        return "Harm to People\nHarm to an Organization\nHarm to an Ecosystem", 91.2

    monkeypatch.setattr("rag_lab.ingestion.extract.ocr_image", ocr)
    page = parse_pdf(fixture_page(2)).pages[0]
    assert page.method == "hybrid"
    assert "Risk Measurement" in page.text
    assert "Harm to People" in page.text
    assert page.blocks[0].source == "tesseract"
    assert page.ocr_confidence == 91.2
    assert len(seen) == 1
    assert page.vision_status == "disabled"
    assert page.text.index("Harm to People") < page.text.index("Fig. 1.")
    assert page.text.index("Fig. 1.") < page.text.index("Risk Measurement")


def test_diagram_schema_rejects_invented_tables(monkeypatch):
    client_type = httpx.Client

    def response(request):
        payload = json.loads(request.content)
        assert payload["format"] == "json"
        return httpx.Response(
            200,
            json={
                "done": True,
                "response": json.dumps(
                    {"description": "Invented interpretation", "tables": [{"rows": [["fake"]]}]}
                ),
            },
        )

    monkeypatch.setattr(
        "rag_lab.ingestion.vision.httpx.Client",
        lambda **kwargs: client_type(transport=httpx.MockTransport(response), **kwargs),
    )
    with Image.new("RGB", (100, 100), "white") as image, pytest.raises(ValueError):
        analyze(image, "qwen2.5vl:3b")


def test_scan_and_vision_evidence_are_both_retained(monkeypatch):
    monkeypatch.setenv("PDF_VISION_MODEL", "qwen2.5vl:3b")
    monkeypatch.setattr("rag_lab.ingestion.extract.ocr_image", lambda image: ("Scanned prose", 82))
    monkeypatch.setattr(
        "rag_lab.ingestion.extract.analyze",
        lambda image, model, timeout, **kwargs: (
            [
                EvidenceBlock(
                    kind="visual_description",
                    source="local_vision",
                    text="Valid and Reliable forms the base of the diagram.",
                )
            ],
            [],
            1024,
            80,
        ),
    )
    page = parse_pdf(fixture_page(4)).pages[0]
    assert page.method == "ocr"
    assert "Scanned prose" in page.text
    assert "forms the base" not in page.text  # Unverified model prose is not evidence.
    assert "forms the base" in page.blocks[-1].text
    assert page.vision_status == "completed"
    assert page.vision_model == "qwen2.5vl:3b"
    assert page.vision_input_tokens == 1024


def test_unavailable_vision_is_explicit_and_keeps_native_evidence(monkeypatch):
    monkeypatch.setenv("PDF_VISION_MODEL", "qwen2.5vl:3b")

    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("private content must never appear in warnings")

    monkeypatch.setattr("rag_lab.ingestion.extract.analyze", unavailable)
    monkeypatch.setattr("rag_lab.ingestion.extract.ocr_image", lambda image: ("Figure labels", 85))
    page = parse_pdf(fixture_page(2)).pages[0]
    assert page.vision_status == "failed"
    assert "Risk Measurement" in page.text
    assert all("private content" not in warning for warning in page.warnings)


def test_vision_transport_fixed_target_bounded_schema_and_table_cells(monkeypatch):
    client_type = httpx.Client

    def response(request):
        assert str(request.url) == "http://vision:11434/api/generate"
        payload = json.loads(request.content)
        assert payload["images"]
        assert payload["stream"] is False
        assert "Distinguish concentric bands" not in payload["prompt"]
        assert payload["keep_alive"] == "10m"
        assert payload["options"]["num_ctx"] == 4096
        assert payload["options"]["num_predict"] == 512
        assert payload["format"] == "json"
        return httpx.Response(
            200,
            json={
                "done": True,
                "response": json.dumps(
                    {
                        "description": "Two grouped labels",
                        "tables": [{"rows": [["Metric", "Value"], ["Cost", "0.05"]]}],
                        "uncertainties": [],
                    }
                ),
                "prompt_eval_count": 300,
                "eval_count": 100,
            },
        )

    monkeypatch.setattr(
        "rag_lab.ingestion.vision.httpx.Client",
        lambda **kwargs: client_type(transport=httpx.MockTransport(response), **kwargs),
    )
    with Image.new("RGB", (100, 100), "white") as image:
        blocks, warnings, inputs, outputs = analyze(image, "qwen2.5vl:3b", allow_tables=True)
    assert blocks[1].rows[1] == ["Cost", "0.05"]
    assert inputs == 300 and outputs == 100
    assert not warnings


def test_table_cells_cannot_bypass_evidence_limits():
    with pytest.raises(ValueError):
        EvidenceBlock(kind="table", source="local_vision", rows=[["x"] * 21])


def test_legacy_parsed_documents_remain_readable():
    from rag_lab.core.models import ParsedDocument

    old = ParsedDocument.model_validate({"pages": [{"number": 1, "text": "Existing review"}]})
    assert old.parser_version == "pdf-v1"
    assert old.pages[0].blocks == []


def test_all_baseline_pages_are_extracted_before_vision_and_timeouts_do_not_lose_them(monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("PDF_VISION_MODEL", "qwen2.5vl:3b")
    monkeypatch.setattr("rag_lab.ingestion.extract.horizontal_rules", lambda image: [])
    seen_ocr = []
    seen_vision = []

    def ocr(image):
        seen_ocr.append(image.size)
        return "Recovered scan or image evidence", 85

    def vision(image, model, timeout, **kwargs):
        # Both raster-only pages and the three mixed-page images precede the first call.
        assert len(seen_ocr) >= 5
        assert 173 < timeout <= 240
        seen_vision.append(timeout)
        raise httpx.ReadTimeout("sensitive provider message")

    monkeypatch.setattr("rag_lab.ingestion.extract.ocr_image", ocr)
    monkeypatch.setattr("rag_lab.ingestion.extract.analyze", vision)
    parsed = parse_pdf(Path("examples/nist-mixed-fixture.pdf").read_bytes())
    assert len(parsed.pages) == 9
    assert len(seen_vision) == 5  # A failed scan must not suppress unrelated figures.
    assert "also pose risks" in parsed.pages[1].text
    assert "Recovered scan" in parsed.pages[8].text
    assert sum(p.vision_status == "failed" for p in parsed.pages) == 5
    assert "request_timeout" in parsed.pages[2].warnings[-1]
    assert "sensitive provider message" not in parsed.model_dump_json()


def test_exhausted_document_budget_does_not_start_model_calls():
    from rag_lab.core.models import Page
    from rag_lab.ingestion.extract import enrich_visuals

    pages = [Page(number=1, text="Already extracted evidence")]
    enrich_visuals(pages, None, [0], "qwen2.5vl:3b", deadline=0)
    assert pages[0].text == "Already extracted evidence"
    assert pages[0].vision_status == "budget_exceeded"


def test_native_table_does_not_spend_a_vision_call(monkeypatch):
    monkeypatch.setenv("PDF_VISION_MODEL", "qwen2.5vl:3b")

    def unexpected(*args):
        pytest.fail("A recovered native table should not invoke vision")

    monkeypatch.setattr("rag_lab.ingestion.extract.analyze", unexpected)
    page = parse_pdf(fixture_page(7)).pages[0]
    assert page.vision_status == "not_needed"
    assert "GOVERN 2.1:" in page.text
    assert page.blocks[0].source == "pdf_geometry"
