"""Geometry-based text/table extraction. No model or document-specific vocabulary."""

from collections import Counter

from rag_lab.core.models import EvidenceBlock
from rag_lab.ingestion.text_cleanup import repair_wraps

TEXT_SETTINGS = {"x_tolerance": 1, "x_tolerance_ratio": 0.1, "y_tolerance": 3}


def table_text(rows):
    """Explicit cell boundaries survive plain-text retrieval; do not infer merged values."""
    evidence = "\n".join(cell for row in rows for cell in row)
    return "\n".join(
        " | ".join(
            repair_wraps(cell, evidence).replace("\n", " ").replace("|", "\\|") for cell in row
        )
        for row in rows
    )


def extract_tables(page):
    tables = page.find_tables({"text_x_tolerance": 1, "text_x_tolerance_ratio": 0.1})
    if not tables:
        # Some tables have only horizontal rules. Repeated segment endpoints still
        # encode the column boundaries; do not guess columns from prose word alignment.
        edges = [
            e for e in page.horizontal_edges if e["width"] > 20 and 5 < e["top"] < page.height - 5
        ]
        counts = Counter(round(e[key], 1) for e in edges for key in ("x0", "x1"))
        xs = sorted(x for x, count in counts.items() if count >= 3)
        if 3 <= len(xs) <= 12:
            ys = sorted(
                {
                    round(e["top"], 1)
                    for e in edges
                    if round(e["x0"], 1) in xs
                    and round(e["x1"], 1) in xs
                    and e["width"] < xs[-1] - xs[0] - 2
                }
            )
            if len(ys) >= 3:
                region = page.crop((xs[0], ys[0], xs[-1], ys[-1]))
                tables = region.find_tables(
                    {
                        "vertical_strategy": "explicit",
                        "explicit_vertical_lines": xs,
                        "horizontal_strategy": "explicit",
                        "explicit_horizontal_lines": ys,
                        "text_x_tolerance": 1,
                        "text_x_tolerance_ratio": 0.1,
                    }
                )
    result = []
    for table in tables[:12]:
        rows = [[str(cell or "").strip() for cell in row] for row in table.extract(**TEXT_SETTINGS)]
        if len(rows) < 2 or max(map(len, rows), default=0) < 2:
            continue
        result.append(
            EvidenceBlock(
                kind="table",
                source="pdf_geometry",
                bbox=list(table.bbox),
                rows=rows,
                text=table_text(rows),
            )
        )
    return result


def text_outside_tables(page, tables):
    def outside(obj):
        cx = (obj.get("x0", 0) + obj.get("x1", 0)) / 2
        cy = (obj.get("top", 0) + obj.get("bottom", 0)) / 2
        return not any(
            b.bbox[0] <= cx <= b.bbox[2] and b.bbox[1] <= cy <= b.bbox[3] for b in tables
        )

    return page.filter(outside).extract_text(**TEXT_SETTINGS) or ""
