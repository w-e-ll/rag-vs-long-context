"""Conservative ruled raster-table recovery with OCR coordinates, without inference."""

from collections import defaultdict

from rag_lab.core.models import EvidenceBlock
from rag_lab.ingestion.layout import table_text


def horizontal_rules(image):
    scale = min(1, 900 / image.width)
    gray = image.convert("L").resize((round(image.width * scale), round(image.height * scale)))
    pixels = gray.load()
    rules = []
    for y in range(gray.height):
        start = None
        for x in range(gray.width + 1):
            dark = x < gray.width and pixels[x, y] < 180
            if dark and start is None:
                start = x
            elif not dark and start is not None:
                if x - start > gray.width * 0.5:
                    if not rules or y - rules[-1][2] > 3:
                        rules.append((start, x, y))
                start = None
    gray.close()
    return [(a / scale, b / scale, y / scale) for a, b, y in rules]


def recover_table(image, data, rules):
    words = [
        (
            data["text"][i].strip(),
            data["left"][i],
            data["top"][i],
            data["left"][i] + data["width"][i],
            data["height"][i],
        )
        for i in range(len(data["text"]))
        if data["text"][i].strip()
    ]

    def text(items):
        lines = defaultdict(list)
        # Geometric baselines avoid Tesseract's page-wide interleaving.
        for word in sorted(items, key=lambda w: w[2] + w[4]):
            baseline = word[2] + word[4]
            key = next((y for y in lines if abs(y - baseline) < word[4] * 0.65), baseline)
            lines[key].append(word)
        return "\n".join(
            " ".join(w[0] for w in sorted(line, key=lambda w: w[1])) for line in lines.values()
        )

    for i in range(len(rules) - 2):
        left, right, top = rules[i]
        header_bottom = rules[i + 1][2]
        if not 5 < header_bottom - top < image.height * 0.04:
            continue
        headers = sorted(
            [w for w in words if top < w[2] < header_bottom and left <= w[1] < right],
            key=lambda w: w[1],
        )
        cuts = [
            (a[3] + b[1]) / 2
            for a, b in zip(headers, headers[1:])
            if b[1] - a[3] > max(image.width * 0.015, a[4])
        ]
        if not 1 <= len(cuts) <= 5:
            continue
        aligned = [
            r[2]
            for r in rules[i:]
            if abs(r[0] - left) < image.width * 0.01 and abs(r[1] - right) < image.width * 0.01
        ]
        if len(aligned) < 3:
            continue
        aligned = sorted(set([*aligned, header_bottom]))
        bottom = aligned[-1]
        inside = [w for w in words if top < w[2] < bottom and left <= w[1] < right]
        # Reject an inferred gutter that cuts through words.
        if any(w[1] + 2 < cut < w[3] - 2 for w in inside for cut in cuts):
            continue
        rows = []
        for y0, y1 in zip(aligned, aligned[1:]):
            row = []
            bounds = [left, *cuts, right]
            for x0, x1 in zip(bounds, bounds[1:]):
                row.append(
                    text([w for w in inside if y0 < w[2] < y1 and x0 <= (w[1] + w[3]) / 2 < x1])
                )
            rows.append(row)
        if len(rows) < 2 or any(not cell for cell in rows[0]):
            continue
        block = EvidenceBlock(
            kind="table",
            source="tesseract",
            rows=rows,
            text=table_text(rows),
            bbox=[v / 3 for v in (left, top, right, bottom)],
        )
        return block, text([w for w in words if w not in inside])
    return None
