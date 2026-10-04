import io
import shutil
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from rag_lab.ingestion.extract import parse_pdf


def test_real_nist_text_and_table():
    reader = PdfReader("examples/nist-ai-rmf-original.pdf")
    writer = PdfWriter()
    writer.add_page(reader.pages[24])
    writer.add_page(reader.pages[27])
    data = io.BytesIO()
    writer.write(data)
    parsed = parse_pdf(data.getvalue())
    assert "GOVERN" in parsed.pages[0].text
    assert "GOVERN 1.5" in parsed.pages[1].text
    assert parsed.pages[0].warnings


def test_reject_encrypted_pdf():
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.encrypt("secret")
    data = io.BytesIO()
    writer.write(data)
    with pytest.raises(ValueError):
        parse_pdf(data.getvalue())


def test_fixture_ocr_pages_have_no_text_layer():
    pages = PdfReader("examples/nist-mixed-fixture.pdf").pages
    assert len(pages) == 9
    assert not pages[4].extract_text()
    assert not pages[8].extract_text()


@pytest.mark.skipif(
    not shutil.which("tesseract"), reason="Tesseract is provided in the Docker parser image"
)
def test_local_ocr_mixed_document():
    parsed = parse_pdf(Path("examples/nist-mixed-fixture.pdf").read_bytes())
    assert parsed.pages[4].method == "ocr"
    assert parsed.pages[8].method == "ocr"
    assert "MAP" in parsed.pages[8].text
    assert "Harm to People" in parsed.pages[2].text
    assert "AI Risks and Trustworthiness" in parsed.pages[4].text
    assert parsed.pages[4].ocr_confidence is not None
    assert parsed.pages[7].blocks[0].rows[0] == ["Categories", "Subcategories"]
