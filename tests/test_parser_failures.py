import httpx
import pytest

from rag_lab.core.errors import AppError
from rag_lab.ingestion.errors import check_parser_response


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"error": "parser_timeout"}, "parser_timeout"),
        ({"error": "ocr_failed"}, "ocr_failed"),
        ({"error": "SECRET_DOCUMENT_TEXT"}, "extraction_failed"),
        ({"error": ["SECRET_DOCUMENT_TEXT"]}, "extraction_failed"),
    ],
)
def test_worker_preserves_only_safe_parser_codes(payload, expected):
    response = httpx.Response(422, json=payload)
    with pytest.raises(AppError) as error:
        check_parser_response(response)
    assert error.value.code == expected
    assert "SECRET" not in str(error.value)
    assert "SECRET" not in error.value.message


def test_parser_busy_remains_retryable():
    response = httpx.Response(
        429,
        json={"error": "parser_busy"},
        request=httpx.Request("POST", "http://parser:8010/parse"),
    )
    with pytest.raises(AppError) as error:
        check_parser_response(response)
    assert error.value.code == "parser_busy"
