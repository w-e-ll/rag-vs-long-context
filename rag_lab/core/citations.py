"""Check page-reference membership, never semantic correctness of a claim."""

import re

ABSTENTION = "Insufficient evidence in the supplied reference."


def source_id(page: int) -> str:
    return f"S{page:03d}"


def is_abstention(text: str) -> bool:
    # Whole-answer match only: an introductory refusal must not hide later claims.
    return text.strip() == ABSTENTION


def source_text(text: str) -> str:
    # Omit standalone folios only in inference context, never in stored evidence.
    return re.sub(r"(?im)^[ \t]*Page[ \t]+\d+[ \t]*$", "", text)


def citation_warnings(text: str, allowed_pages: set[int]) -> list[str]:
    if is_abstention(text):
        return []
    canonical = re.findall(r"\[(S\d+)\]", text)
    compound = re.findall(r"\[(S\d+)\s*[,;:][^\]\n]*\]", text)
    mentioned = re.findall(r"\b(?:PDF\s+|Source\s+)?Pages?\s+\[?(\d+)", text, re.I)
    warnings = []
    if not canonical and not compound:
        warnings.append("No citation in the required [Snnn] format; review the answer.")
    if compound:
        warnings.append(
            "Compound citations detected: use [Snnn] alone. "
            "Added figure/region details are not verified."
        )
    elif re.search(r"\bfigure\s+region\s+\d+", text, re.I):
        warnings.append("OCR region references are not verified source locations; review them.")
    unknown = sorted(set(canonical + compound) - {source_id(p) for p in allowed_pages})
    if unknown:
        warnings.append("Unknown source identifiers: " + ", ".join(unknown))
    invalid = sorted({int(p) for p in mentioned} - allowed_pages)
    if invalid:
        warnings.append(
            "References pages outside supplied evidence: " + ", ".join(map(str, invalid))
        )
    if mentioned:
        warnings.append(
            "Non-standard page references detected; verify PDF versus printed numbering."
        )
    return warnings
