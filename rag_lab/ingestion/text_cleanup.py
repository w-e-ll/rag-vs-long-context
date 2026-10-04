"""Conservative line-wrap repair, without guessing OCR characters or numbers."""

import re


def repair_wraps(text, evidence=""):
    vocabulary = set(re.findall(r"\b[a-zA-Z]{3,}\b", text + "\n" + evidence))

    def joined(match):
        left, right = match.group(1), match.group(2)
        whole = left + right
        return whole if whole in vocabulary else left + "-" + right

    # Visible hyphens can be lexical. Only corroborated complete spellings lose them.
    repaired = re.sub(r"([a-zA-Z]+)-[ \t]*\n[ \t]*([a-z]+)", joined, text)

    # Keep OCR correction deliberately narrow and auditable. These labels are
    # fixed terms in the supported NIST examples; do not generalize this to
    # arbitrary words, identifiers, or numbers where a human must review OCR.
    repaired = re.sub(r"\bAl(?=\s+Model\b)", "AI", repaired)
    repaired = re.sub(r"\bMAP\s+I(?=\s*[:.])", "MAP 1", repaired)
    return repaired
