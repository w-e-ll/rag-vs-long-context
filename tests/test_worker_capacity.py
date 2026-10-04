from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from rag_lab import worker
from rag_lab.core.errors import AppError


@pytest.mark.parametrize("attempt", [1, 3])
def test_busy_parser_defers_without_exhausting_attempts(monkeypatch, attempt):
    repo = Mock()
    job = {"id": uuid4(), "kind": "parse", "attempts": attempt, "lease_token": uuid4()}
    provider = SimpleNamespace(config=SimpleNamespace(lease_seconds=120))
    monkeypatch.setattr(worker, "execute", Mock(side_effect=AppError("parser_busy", "Busy")))
    tenant = uuid4()
    worker.run_one(repo, None, tenant, job, provider)
    repo.retry.assert_called_once_with(tenant, job, capacity_wait=True)
    repo.fail.assert_not_called()


def test_real_parser_failure_is_not_a_capacity_wait(monkeypatch):
    repo = Mock()
    job = {"id": uuid4(), "kind": "parse", "attempts": 1, "lease_token": uuid4()}
    provider = SimpleNamespace(config=SimpleNamespace(lease_seconds=120))
    monkeypatch.setattr(worker, "execute", Mock(side_effect=AppError("ocr_failed", "Failed")))
    tenant = uuid4()
    worker.run_one(repo, None, tenant, job, provider)
    repo.fail.assert_called_once_with(tenant, job, "ocr_failed")
    repo.retry.assert_not_called()
