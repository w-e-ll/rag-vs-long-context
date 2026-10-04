"""Metadata-only JSON events and stack frames without exception messages or locals."""

import json
import logging
import traceback
from datetime import UTC, datetime

LOG = logging.getLogger("rag_lab")
ALLOWED = {
    "request_id",
    "tenant_id",
    "document_id",
    "job_id",
    "run_id",
    "stage",
    "status",
    "duration_ms",
    "attempt",
    "code",
    "count",
    "frames",
    "error_type",
}


def configure():
    if not LOG.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOG.addHandler(handler)
        LOG.propagate = False
    LOG.setLevel(logging.INFO)


def event(name: str, **fields):
    LOG.info(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": name,
                **{k: str(v) for k, v in fields.items() if k in ALLOWED},
            }
        )
    )


def failure(name: str, exc: Exception, **fields):
    frames = [
        {
            "file": f.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
            "line": f.lineno,
            "function": f.name,
        }
        for f in traceback.extract_tb(exc.__traceback__)
    ]
    event(name, error_type=type(exc).__name__, frames=frames, **fields)
