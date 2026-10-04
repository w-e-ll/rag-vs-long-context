"""Bounded OCR of separated colored regions and circular label bands."""

import math
from collections import defaultdict

import pytesseract
from PIL import Image, ImageDraw, ImageOps


def colored_regions(image):
    small = image.convert("RGB")
    small.thumbnail((300, 300))
    width, height = small.size
    pixels = small.load()
    active = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if max(pixels[x, y]) - min(pixels[x, y]) > 45
    }
    regions = []
    while active:
        point = active.pop()
        pending, component = [point], [point]
        while pending:
            x, y = pending.pop()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in active:
                    active.remove(neighbor)
                    pending.append(neighbor)
                    component.append(neighbor)
        if len(component) < width * height * 0.006:
            continue
        x0, x1 = min(x for x, y in component), max(x for x, y in component)
        y0, y1 = min(y for x, y in component), max(y for x, y in component)
        if x1 - x0 < width * 0.08 or y1 - y0 < height * 0.08:
            continue
        regions.append(
            (
                max(0, x0 * image.width / width - 3),
                max(0, y0 * image.height / height - 3),
                min(image.width, (x1 + 1) * image.width / width + 3),
                min(image.height, (y1 + 1) * image.height / height + 3),
                len(component) / ((x1 - x0 + 1) * (y1 - y0 + 1)),
            )
        )
    small.close()
    # Different colors can be disconnected inside one circular figure.
    merged = []
    for box in sorted(regions, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
        owner = next(
            (
                i
                for i, b in enumerate(merged)
                if b[0] - 5 <= box[0]
                and b[1] - 5 <= box[1]
                and b[2] + 5 >= box[2]
                and b[3] + 5 >= box[3]
            ),
            None,
        )
        if owner is None:
            merged.append(box)
        else:
            b = merged[owner]
            density = b[4] + box[4] * (box[2] - box[0]) * (box[3] - box[1]) / (
                (b[2] - b[0]) * (b[3] - b[1])
            )
            merged[owner] = (*b[:4], min(1, density))
    regions = merged
    return sorted(regions, key=lambda b: (round(b[1] / 30), b[0]))


def read_labels(image, psm=11):
    data = pytesseract.image_to_data(
        image, lang="eng", config=f"--psm {psm}", timeout=8, output_type=pytesseract.Output.DICT
    )
    lines = defaultdict(list)
    for i, word in enumerate(data["text"]):
        if word.strip():
            lines[(data["block_num"][i], data["par_num"][i], data["line_num"][i])].append(
                (word.strip(), float(data["conf"][i]))
            )
    return [
        " ".join(word for word, _ in words)
        for words in lines.values()
        if min(c for _, c in words) >= 45
        and sum(c for _, c in words) / len(words) >= 80
        and (
            sum(ch.isalpha() for word, _ in words for ch in word) >= 3
            or " ".join(word for word, _ in words) == "&"
        )
    ]


def unwrap(image, box, inner, outer):
    x0, y0, x1, y1, _ = box
    radius = min(x1 - x0, y1 - y0) / 2
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    width, height = (
        round(2 * math.pi * radius * (inner + outer) / 2),
        round(radius * (outer - inner)),
    )
    strip = Image.new("RGB", (width, height), "white")
    dst, src = strip.load(), image.load()
    for x in range(width):
        angle = 2 * math.pi * x / width - math.pi
        for y in range(height):
            r = radius * outer - y
            xx, yy = round(cx + r * math.sin(angle)), round(cy - r * math.cos(angle))
            if 0 <= xx < image.width and 0 <= yy < image.height:
                dst[x, y] = src[xx, yy]
    return strip


def read_band_windows(mask):
    """Isolate labels so an upside-down neighbour cannot spoil a whole OCR line."""
    labels = []
    for index in range(4):
        left = max(0, round(mask.width * (index / 4 - 0.025)))
        right = min(mask.width, round(mask.width * ((index + 1) / 4 + 0.025)))
        with mask.crop((left, 0, right, mask.height)) as crop:
            # Whitespace avoids edge clipping; upsampling stabilizes small glyphs.
            with crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS) as large:
                with ImageOps.expand(large, border=20, fill="white") as padded:
                    labels.extend(read_labels(padded, 6))
    return labels


def unique_labels(labels):
    """Merge case/whitespace-only OCR variants without guessing letters or meaning."""
    seen, result = set(), []
    for label in labels:
        key = " ".join(label.casefold().split())
        if key not in seen:
            seen.add(key)
            result.append(label)
    return result


def oriented_label(image):
    """Choose one complete OCR hypothesis per region, never union both orientations."""
    candidates = []
    for angle in (0, 180):
        with image.rotate(angle) as rotated:
            with ImageOps.expand(rotated, border=20, fill="white") as padded:
                data = pytesseract.image_to_data(
                    padded,
                    lang="eng",
                    config="--psm 7",
                    timeout=8,
                    output_type=pytesseract.Output.DICT,
                )
        words = [
            (w.strip(), float(c))
            for w, c in zip(data["text"], data["conf"])
            if any(ch.isalnum() for ch in w)
        ]
        if not words:
            continue
        score = sum(c * len(w) for w, c in words) / sum(len(w) for w, _ in words)
        if min(c for _, c in words) >= 45 and score >= 80:
            candidates.append((score, " ".join(w for w, _ in words)))
    return max(candidates, default=(0, ""))


def read_band_regions(strip, light_text):
    """Locate separated label ink before OCR, avoiding clipped overlapping windows."""
    with strip.convert("L") as gray:
        mask = gray.point(lambda v: 0 if (v > 220 if light_text else v < 100) else 255)
    try:
        with mask.crop((0, int(mask.height * 0.23), mask.width, int(mask.height * 0.77))) as middle:
            pixels = middle.load()
            active = [
                x
                for x in range(middle.width)
                if 1 < sum(pixels[x, y] == 0 for y in range(middle.height)) < middle.height * 0.8
            ]
            groups = []
            for x in active:
                if not groups or x - groups[-1][-1] > middle.height * 0.25:
                    groups.append([])
                groups[-1].append(x)
            labels = []
            for group in groups[:16]:
                if len(group) < 10:
                    continue
                box = (
                    max(0, group[0] - 4),
                    int(strip.height * 0.23),
                    min(strip.width, group[-1] + 5),
                    int(strip.height * 0.77),
                )
                candidates = []
                for source in (strip, mask):
                    with source.crop(box) as crop:
                        candidates.append(oriented_label(crop))
                        if candidates[-1][1]:
                            break
                        with crop.resize(
                            (crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS
                        ) as large:
                            candidates.append(oriented_label(large))
                        if candidates[-1][1]:
                            break
                score, label = max(candidates)
                if label:
                    labels.append(label)
            return unique_labels(labels)
    finally:
        mask.close()


def recover_figure(image):
    """Return region labels only; no inferred arrows, categories or descriptions."""
    regions = colored_regions(image)
    if 2 <= len(regions) <= 12:
        pieces = []
        for i, box in enumerate(regions, 1):
            with image.crop(box[:4]) as crop:
                with ImageOps.expand(crop, border=20, fill="white") as padded:
                    labels = read_labels(padded, 6)
                    if not labels:
                        labels = read_labels(padded, 7)
                if box[4] > 0.5 and not labels:
                    with crop.convert("L").point(lambda v: 0 if v > 220 else 255) as mask:
                        # Inversion turns white outside rounded boxes into black edges.
                        # Remove only edge-connected ink, preserving interior glyphs.
                        edges = [
                            (x, y) for x in range(mask.width) for y in (0, mask.height - 1)
                        ] + [(x, y) for y in range(mask.height) for x in (0, mask.width - 1)]
                        for point in edges:
                            if mask.getpixel(point) == 0:
                                ImageDraw.floodfill(mask, point, 255)
                        with ImageOps.expand(mask, border=20, fill="white") as padded:
                            labels = read_labels(padded, 6)
                            if not labels:
                                labels = read_labels(padded, 7)
                            if not labels:
                                with padded.resize(
                                    (padded.width * 2, padded.height * 2), Image.Resampling.LANCZOS
                                ) as large:
                                    labels = read_labels(large, 6)
            if labels:
                pieces.append(f"[Figure region {i}]\n" + "\n".join(labels))
        return "\n\n".join(pieces)
    if len(regions) != 1:
        return ""
    box = regions[0]
    ratio = (box[2] - box[0]) / (box[3] - box[1])
    if not 0.92 < ratio < 1.08 or not 0.55 < box[4] < 0.85:
        return ""
    pieces = []
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    radius = (box[2] - box[0]) / 2
    with image.crop(
        (cx - radius * 0.23, cy - radius * 0.23, cx + radius * 0.23, cy + radius * 0.23)
    ) as center:
        labels = read_labels(center, 6)
        with center.convert("L").point(lambda v: 0 if v > 220 else 255) as mask:
            alternative = read_labels(mask, 6)
            if len(alternative) > len(labels):
                labels = alternative
        labels = unique_labels(labels)
        if labels:
            pieces.append("[Center labels / OCR]\n" + "\n".join(labels))
    for name, inner, outer in (("Inner band", 0.3, 0.65), ("Outer band", 0.6, 1.02)):
        with unwrap(image, box, inner, outer) as strip:
            labels = read_band_regions(strip, light_text=inner == 0.3)
        if labels:
            pieces.append(f"[{name} labels / OCR; reading order unverified]\n" + "\n".join(labels))
    return "\n\n".join(pieces)
