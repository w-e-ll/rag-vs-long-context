"""Keep words in detected side-by-side panel columns instead of joining across them."""

from collections import Counter, defaultdict


def colored_figure_box(image):
    """Bound colored artwork on scans, leaving original OCR and page intact."""
    small = image.convert("RGB")
    small.thumbnail((400, 400))
    points = [
        (x, y)
        for y in range(small.height)
        for x in range(small.width)
        if max(small.getpixel((x, y))) - min(small.getpixel((x, y))) > 50
        and min(small.getpixel((x, y))) < 190
    ]
    width, height = small.size
    small.close()
    if len(points) < width * height * 0.015:
        return None
    x0, x1 = min(x for x, _ in points), max(x for x, _ in points)
    y0, y1 = min(y for _, y in points), max(y for _, y in points)
    if (x1 - x0) * (y1 - y0) > width * height * 0.8:
        return None
    return (
        max(0, x0 * image.width / width - 12),
        max(0, y0 * image.height / height - 12),
        min(image.width, (x1 + 1) * image.width / width + 12),
        min(image.height, (y1 + 1) * image.height / height + 12),
    )


def normalize_marker(word, image):
    """Replace OCR lookalikes only when the glyph is a small colored mark."""
    if word["text"] not in {"e", "©", "®", "•"}:
        return
    crop = image.crop((word["left"], word["top"], word["right"], word["bottom"]))
    crop.thumbnail((32, 32))
    rgb = crop.convert("RGB")
    ink = [
        rgb.getpixel((x, y))
        for y in range(rgb.height)
        for x in range(rgb.width)
        if min(rgb.getpixel((x, y))) < 180
    ]
    colored = sum(max(p) - min(p) > 70 for p in ink)
    if ink and colored / len(ink) > 0.5:
        word["text"] = "•"
    rgb.close()
    crop.close()


def panel_columns(image):
    """Conservative colored-header detector; no document-specific colors or vocabulary."""
    scale = min(1, 512 / image.width)
    small = image.convert("RGB").resize((round(image.width * scale), round(image.height * scale)))
    pixels = small.load()
    patterns, extents = Counter(), {}
    for y in range(small.height):
        active = []
        for x in range(small.width):
            rgb = pixels[x, y]
            active.append(max(rgb) - min(rgb) > 35 and 45 < max(rgb) < 240)
        runs, start = [], None
        for x, value in enumerate(active + [False]):
            if value and start is None:
                start = x
            elif not value and start is not None:
                if x - start >= small.width * 0.12:
                    runs.append((start, x))
                start = None
        if not 2 <= len(runs) <= 6:
            continue
        if any(b[0] - a[1] < small.width * 0.01 for a, b in zip(runs, runs[1:])):
            continue
        key = tuple((round(a / 4) * 4, round(b / 4) * 4) for a, b in runs)
        patterns[key] += 1
        extents.setdefault(key, []).append(y)
    small.close()
    if not patterns:
        return None
    key, count = patterns.most_common(1)[0]
    if count < 4:
        return None
    left, right = key[0][0] / scale, key[-1][1] / scale
    cuts = [(a[1] + b[0]) / (2 * scale) for a, b in zip(key, key[1:])]
    return left, right, min(extents[key]) / scale, max(extents[key]) / scale, cuts


def ordered_text(data, image):
    words = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        words.append(
            {
                "text": word.strip(),
                "left": data["left"][i],
                "top": data["top"][i],
                "right": data["left"][i] + data["width"][i],
                "bottom": data["top"][i] + data["height"][i],
                "line": (data["block_num"][i], data["par_num"][i], data["line_num"][i]),
            }
        )

    def lines(items):
        groups = defaultdict(list)
        for word in items:
            groups[word["line"]].append(word)
        return "\n".join(
            " ".join(w["text"] for w in sorted(line, key=lambda w: w["left"]))
            for line in sorted(groups.values(), key=lambda line: min(w["top"] for w in line))
        )

    layout = panel_columns(image)
    if not layout:
        return lines(words)
    left, right, top, header_bottom, cuts = layout
    # A word crossing a panel gutter below the headers marks the next spanning text region.
    spanning = [
        w
        for w in words
        if w["top"] > header_bottom + 5
        and sum(c.isalnum() for c in w["text"]) >= 4
        and any(w["left"] + 3 < cut < w["right"] - 3 for cut in cuts)
    ]
    first = min(spanning, key=lambda w: w["top"]) if spanning else None
    bottom = (
        min(w["top"] for w in words if w["line"] == first["line"]) - 3 if first else image.height
    )
    before, after, columns = [], [], [[] for _ in range(len(cuts) + 1)]
    for word in words:
        if word["top"] < top - 3:
            before.append(word)
        elif word["top"] >= bottom or word["right"] < left or word["left"] > right:
            after.append(word)
        else:
            center = (word["left"] + word["right"]) / 2
            columns[sum(center > cut for cut in cuts)].append(word)
    if any(len(column) < 3 for column in columns):
        return lines(words)
    for column in columns:
        for word in column:
            normalize_marker(word, image)
    pieces = [lines(before)]
    pieces.extend(f"[Panel column {i}]\n{lines(column)}" for i, column in enumerate(columns, 1))
    pieces.append(lines(after))
    return "\n\n".join(piece for piece in pieces if piece)
