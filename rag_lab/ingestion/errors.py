"""Allowlisted parser failures. Never pass through remote exception messages."""

import httpx

from rag_lab.core.errors import AppError

PARSER_ERRORS = {
    "parser_timeout": "Document extraction exceeded the parser deadline.",
    "extraction_failed": "The PDF parser could not extract the document.",
    "parser_resource_limit": "The PDF parser reached its process resource limit.",
    "parser_process_stopped": "The PDF parser process was terminated by a signal.",
    "ocr_unavailable": "The local OCR executable is unavailable.",
    "ocr_failed": "Local OCR could not complete for a scanned page.",
    "too_large": "The PDF exceeds the parser size limit.",
    "upload_timeout": "Transfer to the PDF parser exceeded its deadline.",
}


def check_parser_response(response):
    if response.status_code == 429:
        raise AppError("parser_busy", "The parser is busy; extraction remains queued.", 429)
    # Preserve the existing transient HTTP retry path for busy/unavailable services.
    if response.status_code in {502, 503, 504}:
        response.raise_for_status()
    if response.is_error:
        try:
            body = response.json()
            code = body.get("error") if isinstance(body, dict) else None
        except ValueError:
            code = None
        if not isinstance(code, str) or code not in PARSER_ERRORS:
            code = "extraction_failed"
        raise AppError(code, PARSER_ERRORS[code])
    # Reject redirects instead of parsing their possibly misleading response bodies.
    if response.status_code != httpx.codes.OK:
        raise AppError("extraction_failed", PARSER_ERRORS["extraction_failed"])
