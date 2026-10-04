"""Executed only inside an isolated, resource-bounded parser subprocess."""

import io
import json
import os
import re
import sys
import time

import httpx
import pdfplumber
import pypdfium2 as pdfium
import pytesseract
from PIL import ImageDraw
from pypdf import PdfReader

from rag_lab.core.models import EvidenceBlock, Page, ParsedDocument
from rag_lab.ingestion.budgets import (
    ENRICHMENT_DEADLINE_SECONDS,
    VISION_CALL_SECONDS,
    VISION_PASS_SECONDS,
)
from rag_lab.ingestion.figure_ocr import recover_figure
from rag_lab.ingestion.layout import TEXT_SETTINGS, extract_tables, text_outside_tables
from rag_lab.ingestion.ocr_layout import colored_figure_box, ordered_text
from rag_lab.ingestion.scan_tables import horizontal_rules, recover_table
from rag_lab.ingestion.text_cleanup import repair_wraps
from rag_lab.ingestion.vision import analyze


def ocr_image(image):
    data = pytesseract.image_to_data(
        image,
        lang="eng",
        config="--psm 3",
        timeout=30,
        output_type=pytesseract.Output.DICT,
    )
    confidence = []
    for i, word in enumerate(data["text"]):
        if word.strip():
            score = float(data["conf"][i])
            if score >= 0:
                confidence.append(score)
    return ordered_text(data, image), (sum(confidence) / len(confidence) if confidence else 0)


def extract_page(page, raster_page, number):
    started = time.perf_counter()
    tables = extract_tables(page)
    text = text_outside_tables(page, tables)
    native = page.extract_text(**TEXT_SETTINGS) or ""
    scanned = len(native.strip()) < 60
    result = Page(
        number=number,
        text="",
        blocks=tables,
        vision_status="disabled",
    )
    # Small rules (including page headers) alone are not visual figures.
    visual = bool(page.images or tables or len(page.curves) > 4 or len(page.lines) > 8)
    image = None
    scan_order = None
    if scanned or page.images:
        bitmap = raster_page.render(scale=3)
        try:
            image = bitmap.to_pil().copy()
        finally:
            bitmap.close()
    try:
        if scanned:
            text, result.ocr_confidence = ocr_image(image)
            result.method = "ocr"
            rules = horizontal_rules(image)
            if len(rules) >= 3:
                try:
                    data = pytesseract.image_to_data(
                        image,
                        lang="eng",
                        config="--psm 3",
                        timeout=30,
                        output_type=pytesseract.Output.DICT,
                    )
                    recovered = recover_table(image, data, rules)
                    if recovered:
                        table, text = recovered
                        result.blocks.append(table)
                        result.warnings.append(
                            "Scan table recovered from ruling lines and OCR positions; "
                            "verify cell values and merged cells."
                        )
                except (RuntimeError, pytesseract.TesseractNotFoundError):
                    result.warnings.append("Scan table OCR unavailable; baseline OCR preserved.")
            if not result.blocks:
                box = colored_figure_box(image)
                if box and box[1] >= 1 and box[3] < image.height - 1:
                    try:
                        with image.crop(box) as crop:
                            figure = recover_figure(crop)
                        if figure:
                            # Read prose independently: panel heuristics must never consume
                            # the caption or surrounding paragraphs on a full-page scan.
                            with image.crop((0, 0, image.width, int(box[1]))) as above:
                                before, _ = ocr_image(above)
                            with image.crop((0, int(box[3]), image.width, image.height)) as below:
                                after, _ = ocr_image(below)
                            result.blocks.append(
                                EvidenceBlock(
                                    kind="image_text",
                                    source="tesseract",
                                    text=figure,
                                    bbox=[v / 3 for v in box],
                                )
                            )
                            scan_order = "\n\n".join(
                                (before, "[image_text / tesseract]\n" + figure, after)
                            )
                    except (RuntimeError, pytesseract.TesseractNotFoundError):
                        result.warnings.append("Scan figure OCR unavailable; baseline preserved.")
            result.warnings.append("Scan OCR: check reading order, numbers and table cells.")
            if not text.strip():
                result.warnings.append("No readable text recovered from the scan.")
        elif page.images:
            result.method = "hybrid"
            regions = []
            for obj in page.images:
                box = (
                    max(0, obj["x0"]),
                    max(0, obj["top"]),
                    min(page.width, obj["x1"]),
                    min(page.height, obj["bottom"]),
                )
                if box in regions or box[2] - box[0] < 30 or box[3] - box[1] < 20:
                    continue
                regions.append(box)
                if len(regions) > 12:
                    result.warnings.append(
                        "Image OCR region limit reached; review remaining images."
                    )
                    break
                crop = image.crop(tuple(round(v * 3) for v in box))
                # Native captions can overlap an embedded image's bounding box.
                # Mask those glyphs only for OCR; keep the original for vision/review.
                draw = ImageDraw.Draw(crop)
                for char in page.chars:
                    if (
                        char["x1"] > box[0]
                        and char["x0"] < box[2]
                        and char["bottom"] > box[1]
                        and char["top"] < box[3]
                    ):
                        draw.rectangle(
                            [
                                (char["x0"] - box[0]) * 3 - 1,
                                (char["top"] - box[1]) * 3 - 1,
                                (char["x1"] - box[0]) * 3 + 1,
                                (char["bottom"] - box[1]) * 3 + 1,
                            ],
                            fill="white",
                        )
                try:
                    recovered, confidence = ocr_image(crop)
                    if "[Panel column 1]" not in recovered:
                        try:
                            structured = recover_figure(crop)
                            if structured:
                                # Keep the original OCR in provenance, separate from region text.
                                baseline_ocr = recovered
                                recovered = structured
                                result.warnings.append(
                                    "Figure OCR uses separate regions/ring bands; labels may be "
                                    "missing or misread. Region order does not establish "
                                    "relationships."
                                )
                                result.blocks.append(
                                    EvidenceBlock(
                                        kind="image_text",
                                        source="tesseract",
                                        text="[Original figure OCR; not canonical]\n"
                                        + baseline_ocr,
                                    )
                                )
                        except (RuntimeError, pytesseract.TesseractNotFoundError):
                            result.warnings.append(
                                "Region OCR unavailable; original OCR preserved."
                            )
                except (RuntimeError, pytesseract.TesseractNotFoundError):
                    result.warnings.append(
                        "Image OCR unavailable or timed out; image needs review."
                    )
                    continue
                finally:
                    crop.close()
                # Native glyphs were masked before OCR. Do not remove figure labels
                # merely because the same word also occurs in surrounding prose.
                if recovered:
                    result.blocks.append(
                        EvidenceBlock(
                            kind="image_text", source="tesseract", text=recovered, bbox=list(box)
                        )
                    )
                    result.ocr_confidence = min(result.ocr_confidence or 100, confidence)
                else:
                    result.warnings.append("An image has no readable OCR text; inspect visually.")
        if visual or scanned:
            result.warnings.append(
                "Visual structure is unresolved (vision disabled in OCR-first mode): text, "
                "OCR and table evidence are available, but diagram relationships require "
                "visual review."
            )
        if tables:
            result.warnings.append(
                "Tables reconstructed from PDF geometry; empty/merged cells need review. "
                "Values are not carried across pages."
            )
        if result.ocr_confidence is not None and result.ocr_confidence < 70:
            result.warnings.append("Low OCR confidence; review against the source page.")
        # Keep canonical evidence explicit. Both experiment arms consume this same text.
        pieces = [text]
        for block in result.blocks:
            if block.text.startswith("[Original figure OCR; not canonical]"):
                continue
            pieces.append(f"[{block.kind} / {block.source}]\n{block.text}")
        result.text = "\n\n".join(piece for piece in pieces if piece.strip())
        if scan_order is not None:
            result.text = scan_order
        if not scanned and result.blocks:
            result.text = reading_order(page, result.blocks)
        result.warnings = list(dict.fromkeys(result.warnings))[:20]
        result.extraction_ms = (time.perf_counter() - started) * 1000
        return Page.model_validate(result.model_dump())
    finally:
        if image:
            image.close()


def reading_order(page, blocks):
    """Place recovered content near its source; exclude duplicate table characters."""
    tables = [b for b in blocks if b.kind == "table" and b.bbox]

    def outside(obj):
        x = (obj.get("x0", 0) + obj.get("x1", 0)) / 2
        y = (obj.get("top", 0) + obj.get("bottom", 0)) / 2
        return not any(b.bbox[0] <= x <= b.bbox[2] and b.bbox[1] <= y <= b.bbox[3] for b in tables)

    events = [
        (line["top"], line["text"])
        for line in page.filter(outside).extract_text_lines(**TEXT_SETTINGS)
    ]
    for block in blocks:
        if not block.bbox:
            continue
        y = (block.bbox[1] + block.bbox[3]) / 2 if block.kind == "image_text" else block.bbox[1]
        events.append((y, f"\n[{block.kind} / {block.source}]\n{block.text}\n"))
    return "\n".join(text for _, text in sorted(events, key=lambda item: item[0]))


def enrich_visuals(pages, rendered, candidates, model, deadline):
    """Optional second pass: baseline evidence is complete before any model call."""
    deadline = min(deadline, time.monotonic() + VISION_PASS_SECONDS)
    # Scanned tables need vision more than native tables already recovered as cells.
    candidates.sort(
        key=lambda i: (
            pages[i].method != "ocr",
            bool(pages[i].blocks and pages[i].blocks[0].source == "pdf_geometry"),
            i,
        )
    )
    for attempt, index in enumerate(candidates):
        page = pages[index]
        remaining = deadline - time.monotonic()
        page.vision_model = model
        if remaining < 10 or attempt >= 10:
            page.vision_status = "budget_exceeded"
            page.warnings.append(
                "Vision was not invoked: document time/call budget exhausted; baseline preserved."
            )
            page.warnings = page.warnings[:20]
            continue
        start = time.perf_counter()
        raster = rendered[index]
        image = None
        try:
            bitmap = raster.render(scale=2)
            try:
                image = bitmap.to_pil().copy()
            finally:
                bitmap.close()
            # Mixed pages already have native prose; focus vision on image regions.
            boxes = [b.bbox for b in page.blocks if b.kind == "image_text" and b.bbox]
            if page.method == "hybrid" and boxes:
                box = (
                    max(0, min(b[0] for b in boxes) * 2 - 8),
                    max(0, min(b[1] for b in boxes) * 2 - 8),
                    min(image.width, max(b[2] for b in boxes) * 2 + 8),
                    min(image.height, max(b[3] for b in boxes) * 2 + 8),
                )
                cropped = image.crop(box)
                image.close()
                image = cropped
            elif page.method == "ocr":
                box = colored_figure_box(image)
                if box:
                    cropped = image.crop(box)
                    image.close()
                    image = cropped
            blocks, uncertainties, inputs, outputs = analyze(
                image,
                model,
                min(VISION_CALL_SECONDS, remaining),
                allow_tables=bool(re.search(r"\bTable\s+\d", page.text)),
            )
            # Validate the enriched page before replacing its baseline evidence.
            updated = page.model_copy(deep=True)
            updated.blocks.extend(blocks)
            updated.vision_input_tokens, updated.vision_output_tokens = inputs, outputs
            updated.vision_status = "completed"
            updated.warnings = [
                w for w in updated.warnings if not w.startswith("Visual structure is unresolved")
            ]
            updated.warnings.append(
                "Vision response received, not verified. Suggestions are excluded from "
                "canonical text; copy only verified evidence into the reviewed text."
            )
            if uncertainties:
                updated.warnings.append(
                    "Vision uncertainty: " + "; ".join(note[:300] for note in uncertainties)
                )
            updated.warnings = updated.warnings[:20]
            page = Page.model_validate(updated.model_dump())
            pages[index] = page
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            page.vision_status = "failed"
            if isinstance(exc, httpx.TimeoutException):
                reason = "request_timeout"
            elif isinstance(exc, httpx.ConnectError):
                reason = "service_unavailable"
            elif isinstance(exc, httpx.HTTPError):
                reason = "service_http_error"
            else:
                reason = getattr(exc, "code", "invalid_output")
            page.warnings.append(
                f"Vision failed ({reason}); baseline text/OCR/tables are preserved."
            )
        finally:
            page.warnings = page.warnings[:20]
            page.vision_ms = (time.perf_counter() - start) * 1000
            page.extraction_ms += page.vision_ms
            if image:
                image.close()
            raster.close()


def parse_pdf(raw: bytes) -> ParsedDocument:
    deadline = time.monotonic() + ENRICHMENT_DEADLINE_SECONDS
    if not raw.startswith(b"%PDF-") or len(raw) > 20000000:
        raise ValueError("Invalid PDF")
    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
        raise ValueError("Encrypted PDF or excessive page count")
    root = reader.trailer["/Root"]
    if any(key in root for key in ("/OpenAction", "/AA", "/AcroForm")):
        raise ValueError("Interactive PDF is not supported")
    names = root.get("/Names", {})
    if hasattr(names, "get_object"):
        names = names.get_object()
    if any(key in names for key in ("/JavaScript", "/EmbeddedFiles")):
        raise ValueError("Active or embedded content is not supported")
    pages = []
    vision_model = os.environ.get("PDF_VISION_MODEL", "")
    if vision_model not in {"", "qwen2.5vl:3b"}:
        raise ValueError("Unsupported local vision model")
    candidates = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        rendered = pdfium.PdfDocument(raw)
        try:
            for number, page in enumerate(pdf.pages, 1):
                if page.width * page.height > 1500000:
                    raise ValueError("Page dimensions exceed limit")
                if reader.pages[number - 1].get("/AA"):
                    raise ValueError("Page actions are not supported")
                for annotation in reader.pages[number - 1].get("/Annots", []):
                    annotation = annotation.get_object()
                    action = annotation.get("/A")
                    if action and action.get_object().get("/S") not in {"/URI", "/GoTo"}:
                        raise ValueError("Unsafe annotation action")
                raster_page = rendered[number - 1]
                try:
                    parsed = extract_page(page, raster_page, number)
                finally:
                    raster_page.close()
                if (
                    page.images
                    or parsed.method == "ocr"
                    or len(page.curves) > 4
                    or (len(page.lines) > 8 and not parsed.blocks)
                ) and not (
                    parsed.method == "ocr"
                    and any(b.kind == "table" and b.source == "tesseract" for b in parsed.blocks)
                ):
                    candidates.append(number - 1)
                else:
                    if vision_model:
                        parsed.vision_status = "not_needed"
                    if parsed.blocks:
                        parsed.warnings = [
                            w
                            for w in parsed.warnings
                            if not w.startswith("Visual structure is unresolved")
                        ]
                pages.append(parsed)
            if vision_model:
                enrich_visuals(pages, rendered, candidates, vision_model, deadline)
        finally:
            rendered.close()
    evidence = "\n".join(page.text for page in pages)
    for page in pages:
        original_text = page.text
        page.text = repair_wraps(page.text, evidence)
        if page.text != original_text:
            page.warnings.insert(
                0, "Conservative OCR label normalization applied; verify labels against the PDF."
            )
    return ParsedDocument(pages=pages, parser_version="pdf-v5")


def main():
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (1500000000, 1500000000))
        resource.setrlimit(resource.RLIMIT_CPU, (150, 150))
        resource.setrlimit(resource.RLIMIT_FSIZE, (64000000, 64000000))
    try:
        raw = sys.stdin.buffer.read(20000001)
        result = parse_pdf(raw)
        sys.stdout.write(result.model_dump_json())
    except Exception as exc:
        # No raw parser exceptions, file content, paths or metadata cross this boundary.
        code = "extraction_failed"
        if isinstance(exc, MemoryError):
            code = "parser_resource_limit"
        elif isinstance(exc, pytesseract.TesseractNotFoundError):
            code = "ocr_unavailable"
        elif isinstance(exc, pytesseract.TesseractError):
            code = "ocr_failed"
        sys.stdout.write(json.dumps({"error": code}))
        sys.exit(1)


if __name__ == "__main__":
    main()
