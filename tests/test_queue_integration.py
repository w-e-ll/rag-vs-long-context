"""Run only against explicitly configured isolated test services."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text, update

from rag_lab import queue
from rag_lab.core.config import Settings
from rag_lab.db.schema import jobs

pytestmark = pytest.mark.integration


def test_lost_stream_is_reconstructed_from_postgres(db_repo, monkeypatch):
    url = os.environ.get("TEST_REDIS_URL")
    if not url or not url.endswith("/15"):
        pytest.skip("Set isolated TEST_REDIS_URL ending in /15")
    tenant, doc, name = uuid4(), uuid4(), "test:" + str(uuid4())
    monkeypatch.setattr(queue, "STREAM", name)
    monkeypatch.setattr(queue, "GROUP", name + ":group")
    config = Settings(redis_url=url, _env_file=None)
    redis = queue.client(config)
    try:
        db_repo.create_document(tenant, doc, str(uuid4()), "a" * 64)
        queue.publish(db_repo, redis, [tenant])
        first = redis.xreadgroup(queue.GROUP, "consumer-a", {name: ">"}, count=1)
        job_id = uuid4()  # overwritten only after validating delivery
        from uuid import UUID

        job_id = UUID(first[0][1][0][1]["job_id"])
        lease = db_repo.claim(tenant, 120, job_id)
        assert lease and db_repo.claim(tenant, 120, job_id) is None
        # Simulate lease expiry and loss of this test stream, not any application key.
        with db_repo.transaction(tenant) as conn:
            conn.execute(
                update(jobs)
                .where(jobs.c.tenant_id == tenant, jobs.c.id == job_id)
                .values(
                    lease_until=text("now() - interval '1 minute'"),
                    dispatched_at=text("now() - interval '1 minute'"),
                )
            )
        redis.delete(name)
        redis = queue.client(config)
        queue.publish(db_repo, redis, [tenant])
        second = redis.xreadgroup(queue.GROUP, "consumer-b", {name: ">"}, count=1)
        assert second[0][1][0][1]["job_id"] == str(job_id)
        new_lease = db_repo.claim(tenant, 120, job_id)
        assert new_lease["lease_token"] != lease["lease_token"]
        assert not db_repo.heartbeat(tenant, job_id, lease["lease_token"], 120)
    finally:
        redis.delete(name)
        redis.close()
        db_repo.delete_document(tenant, doc)
