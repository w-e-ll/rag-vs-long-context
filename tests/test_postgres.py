from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from rag_lab.core.errors import AppError
from rag_lab.core.models import Page, ParsedDocument
from rag_lab.db.schema import documents

pytestmark = pytest.mark.integration


def test_capacity_wait_preserves_attempts_and_lease_fencing(db_repo):
    repo = db_repo
    tenant, doc = uuid4(), uuid4()
    try:
        repo.create_document(tenant, doc, str(uuid4()), "c" * 64)
        for _ in range(5):
            job = repo.claim(tenant, 120)
            assert job["attempts"] == 1
            with pytest.raises(AppError):
                repo.retry(tenant, {**job, "lease_token": uuid4()}, capacity_wait=True)
            repo.retry(tenant, job, capacity_wait=True)
            assert job["id"] not in repo.dispatchable(tenant)
        assert repo.document(tenant, doc)["status"] != "failed"
    finally:
        repo.delete_document(tenant, doc)


def test_rls_idempotency_and_claim_fencing(db_repo):
    repo = db_repo
    a, b, doc, key = uuid4(), uuid4(), uuid4(), str(uuid4())
    try:
        assert repo.create_document(a, doc, key, "a" * 64) == (doc, True)
        assert repo.create_document(a, uuid4(), key, "a" * 64) == (doc, False)
        with pytest.raises(AppError):
            repo.create_document(a, uuid4(), key, "b" * 64)
        with pytest.raises(AppError):
            repo.document(b, doc)
        with repo.transaction(b) as conn:
            assert not conn.execute(select(documents).where(documents.c.id == doc)).all()
        with repo.engine.connect() as conn:
            assert not conn.execute(select(documents).where(documents.c.id == doc)).all()
            assert (
                conn.execute(
                    text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")
                ).scalar()
                is False
            )
        with ThreadPoolExecutor(max_workers=3) as pool:
            claims = list(pool.map(lambda _: repo.claim(a, 120), range(3)))
        assert sum(j is not None for j in claims) == 1
        job = next(j for j in claims if j)
        bad = {**job, "lease_token": uuid4()}
        with pytest.raises(AppError):
            repo.save_parsed(a, bad, ParsedDocument(pages=[Page(number=1, text="Evidence")]))
        repo.save_parsed(a, job, ParsedDocument(pages=[Page(number=1, text="Evidence")]))
        assert repo.document(a, doc)["status"] == "review"
    finally:
        repo.delete_document(a, doc)
