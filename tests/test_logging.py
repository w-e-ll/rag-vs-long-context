import logging

from rag_lab.core.logging import LOG, failure


def test_exception_message_and_document_content_are_not_logged():
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Capture()
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    try:
        try:
            raise ValueError("CONFIDENTIAL-PASSWORD")
        except ValueError as exc:
            failure("test.failed", exc, question="PRIVATE-QUESTION")
    finally:
        LOG.removeHandler(handler)
    assert "CONFIDENTIAL-PASSWORD" not in "".join(records)
    assert "PRIVATE-QUESTION" not in "".join(records)
    assert "ValueError" in "".join(records)
    assert "frames" in "".join(records)
