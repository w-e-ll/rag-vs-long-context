import shutil

import pytest
from PIL import Image, ImageDraw

from rag_lab.ingestion.ocr_layout import ordered_text
from tests.test_pdf_v2 import fixture_page


def test_panel_reading_order_and_spanning_caption():
    with Image.new("RGB", (600, 300), "white") as image:
        draw = ImageDraw.Draw(image)
        for x in (20, 220, 420):
            draw.rectangle((x, 20, x + 160, 60), fill=(60, 100, 130))
        data = {
            k: []
            for k in ("text", "left", "top", "width", "height", "block_num", "par_num", "line_num")
        }
        for line, y in enumerate((30, 90, 120), 1):
            for col, x in enumerate((30, 230, 430), 1):
                values = (f"column{col}word{line}", x, y, 130, 15, 1, 1, line)
                for k, v in zip(data, values):
                    data[k].append(v)
        for values in (
            ("Figure", 20, 200, 40, 15, 1, 1, 4),
            ("caption", 160, 202, 110, 15, 1, 1, 4),
        ):
            for k, v in zip(data, values):
                data[k].append(v)
        text = ordered_text(data, image)
    assert text.index("column1word3") < text.index("column2word1")
    assert text.index("column2word3") < text.index("column3word1")
    assert text.endswith("Figure caption")


def check_real_fixture():
    from rag_lab.ingestion.extract import parse_pdf

    page = parse_pdf(fixture_page(2)).pages[0]
    text = page.blocks[0].text
    first, second, third = text.split("[Panel column ")[1:]
    assert "Harm to People" in first and "civil liberties" in first
    assert "business operations" in second and "reputation" in second
    assert "global financial" in third and "natural resources" in third
    assert "business operations" not in first
    assert "global financial" not in second
    assert "Risk Measurement" in page.text
    assert "NIST" not in text  # Native header must not be duplicated through OCR.


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Requires native Tesseract")
def test_real_nist_panel_ocr(monkeypatch):
    monkeypatch.delenv("PDF_VISION_MODEL", raising=False)
    check_real_fixture()


def check_real_scan_table():
    from rag_lab.ingestion.extract import parse_pdf

    page = parse_pdf(fixture_page(8)).pages[0]
    table = next(b for b in page.blocks if b.kind == "table")
    assert table.rows[0] == ["Categories", "Subcategories"]
    assert len(table.rows) == 3
    assert "Context is" in table.rows[1][0]
    assert "MAP 1.1:" in table.rows[1][1] and "MAP 1.6:" in table.rows[1][1]
    assert "MAP 2:" in table.rows[2][0] and "MAP 2.2:" in table.rows[2][1]
    assert "MAP 1.1:" not in table.rows[1][0]
    assert page.text.count("MAP 1.1:") == 1


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Requires native Tesseract")
def test_real_nist_scan_table(monkeypatch):
    monkeypatch.delenv("PDF_VISION_MODEL", raising=False)
    check_real_scan_table()


def test_marker_normalization_requires_color():
    from rag_lab.ingestion.ocr_layout import normalize_marker

    for color, expected in [("orange", "•"), ("black", "e")]:
        with Image.new("RGB", (20, 20), color) as image:
            word = dict(text="e", left=0, top=0, right=20, bottom=20)
            normalize_marker(word, image)
            assert word["text"] == expected


def test_scan_table_rejects_gutter_crossing_words():
    from rag_lab.ingestion.scan_tables import recover_table

    data = dict(
        text=["Left", "Right", "crossing"],
        left=[20, 70, 40],
        top=[22, 22, 40],
        width=[15, 20, 35],
        height=[5, 5, 8],
    )
    with Image.new("RGB", (120, 400), "white") as image:
        assert recover_table(image, data, [(10, 110, 20), (10, 110, 30), (10, 110, 100)]) is None


def test_scan_figure_crop_excludes_prose_and_retains_all_colored_boxes():
    from rag_lab.ingestion.ocr_layout import colored_figure_box

    with Image.new("RGB", (600, 800), "white") as image:
        draw = ImageDraw.Draw(image)
        draw.rectangle((50, 50, 500, 150), fill="black")
        draw.rectangle((100, 400, 500, 500), fill=(60, 100, 150))
        box = colored_figure_box(image)
        assert box[0] <= 100 and box[2] >= 500
        assert 150 < box[1] <= 400 and box[3] >= 500


def check_real_diagrams():
    from rag_lab.ingestion.extract import parse_pdf

    wheel = parse_pdf(fixture_page(3)).pages[0]
    block = next(b for b in wheel.blocks if b.bbox)
    inner = block.text.split("[Inner band labels / OCR; reading order unverified]\n")[1]
    inner, outer = inner.split("\n\n[Outer band labels / OCR; reading order unverified]\n")
    assert len(inner.splitlines()) == 4, inner
    assert len(outer.splitlines()) == 6, outer
    assert "ask" not in inner.splitlines()
    assert "asn pue Aojdeq" not in outer
    assert "Modet" not in inner
    for label in (
        "Plan and Design",
        "Collect and process data",
        "Build and use model",
        "Verify and validate",
        "Deploy and Use",
        "Operate and Monitor",
        "Application Context",
        "Data and Input",
        "Task and Output",
    ):
        assert label.casefold() in block.text.casefold(), (label, block.text)
    assert wheel.text.index("Plan and Design") < wheel.text.index("Fig. 2.")
    core = parse_pdf(fixture_page(5)).pages[0]
    block = next(b for b in core.blocks if b.bbox)
    regions = block.text.split("[Figure region ")[1:]
    assert len(regions) == 4
    for region, label, phrase in zip(
        regions,
        ("Map", "Measure", "Govern", "Manage"),
        ("related to context", "are assessed", "culture of risk", "prioritized"),
    ):
        assert label in region and phrase in region
    assert "Identified risks" not in regions[0]
    assert core.text.index("[Figure region 1]") < core.text.index("Fig. 5.")


def check_real_scan_figure():
    from rag_lab.ingestion.extract import parse_pdf

    page = parse_pdf(fixture_page(4)).pages[0]
    block = next(b for b in page.blocks if b.kind == "image_text")
    regions = block.text.split("[Figure region ")[1:]
    assert len(regions) == 7
    for region, label in zip(
        regions,
        (
            "Safe",
            "Secure &",
            "Explainable &",
            "Privacy-",
            "Fair - With Harmful",
            "Accountable",
            "Valid & Reliable",
        ),
    ):
        assert label in region, region
    assert "&\nTransparent" in regions[5]
    assert "Fig. 4." not in block.text
    assert page.text.count("Fig. 4.") == 1
    assert page.text.index("[Figure region 7]") < page.text.index("Fig. 4.")
    assert "[Panel column" not in page.text


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Requires native Tesseract")
def test_real_scan_figure(monkeypatch):
    monkeypatch.delenv("PDF_VISION_MODEL", raising=False)
    check_real_scan_figure()


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Requires native Tesseract")
def test_real_diagrams(monkeypatch):
    monkeypatch.delenv("PDF_VISION_MODEL", raising=False)
    check_real_diagrams()


def test_orientation_selects_one_hypothesis(monkeypatch):
    from rag_lab.ingestion import figure_ocr

    replies = iter(
        [
            {"text": ["asn", "pue", "Aojdeq"], "conf": [82, 84, 81]},
            {"text": ["Deploy", "and", "Use"], "conf": [96, 96, 96]},
        ]
    )
    monkeypatch.setattr(figure_ocr.pytesseract, "image_to_data", lambda *a, **kw: next(replies))
    with Image.new("RGB", (200, 50), "white") as image:
        assert figure_ocr.oriented_label(image)[1] == "Deploy and Use"
