"""Redis is delivery; PostgreSQL jobs are the transactional outbox and source of truth."""

import json
import time
from uuid import UUID

from prometheus_client import start_http_server
from redis import Redis
from redis.exceptions import ResponseError
from sqlalchemy import func, select

from rag_lab.core.config import settings
from rag_lab.core.logging import configure, event, failure
from rag_lab.core.metrics import QUEUE_AGE, QUEUE_DEPTH, READY
from rag_lab.core.security import Cipher
from rag_lab.db.repository import Repository
from rag_lab.db.schema import jobs

STREAM, GROUP = "rag:jobs", "rag-workers"


def client(config):
    redis = Redis.from_url(
        config.redis_url.get_secret_value(),
        decode_responses=True,
        socket_timeout=10,
        socket_connect_timeout=3,
    )
    try:
        redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    return redis


def publish(repo, redis, tenants):
    counts = {"parse": 0, "index": 0, "compare": 0}
    oldest = 0.0
    for tenant in tenants:
        repo.reap(tenant)
        for job_id in repo.dispatchable(tenant):
            # Publish then mark. A crash can duplicate a notification, never lose the DB job.
            redis.xadd(
                STREAM,
                {"tenant_id": str(tenant), "job_id": str(job_id)},
                maxlen=10000,
                approximate=True,
            )
            repo.mark_dispatched(tenant, job_id)
            event("queue.dispatched", job_id=job_id)
        with repo.transaction(tenant) as conn:
            for kind, count in conn.execute(
                select(jobs.c.kind, func.count())
                .where(jobs.c.tenant_id == tenant, jobs.c.status.in_(["queued", "running"]))
                .group_by(jobs.c.kind)
            ):
                counts[kind] += count
            age = conn.execute(
                select(func.max(func.extract("epoch", func.now() - jobs.c.created_at))).where(
                    jobs.c.tenant_id == tenant, jobs.c.status == "queued"
                )
            ).scalar()
            oldest = max(oldest, float(age or 0))
    for kind, count in counts.items():
        QUEUE_DEPTH.labels(kind).set(count)
    QUEUE_AGE.set(oldest)


def main():
    configure()
    config = settings()
    repo = Repository(config.database_url, Cipher(config.encryption_key.get_secret_value()))
    tenants = {
        UUID(v["tenant_id"])
        for v in json.loads(config.credentials_json.get_secret_value()).values()
    }
    start_http_server(9102)
    while True:
        try:
            publish(repo, client(config), tenants)
            READY.set(1)
        except Exception as exc:
            READY.set(0)
            failure("queue.dispatch_failed", exc)
        time.sleep(3)


if __name__ == "__main__":
    main()
