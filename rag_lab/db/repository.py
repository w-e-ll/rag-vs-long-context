"""All tenant work sets transaction-local RLS context and applies explicit filters."""

import hashlib
import json
from contextlib import contextmanager
from dataclasses import asdict
from uuid import uuid4

from sqlalchemy import create_engine, delete, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from rag_lab.core.chunking import Chunk
from rag_lab.core.errors import AppError
from rag_lab.core.models import ParsedDocument
from rag_lab.db.schema import chunks, documents, embedding_cache, jobs


class Repository:
    def __init__(self, url, cipher):
        self.engine = create_engine(
            url, pool_pre_ping=True, pool_size=5, max_overflow=5, hide_parameters=True
        )
        self.cipher = cipher

    @contextmanager
    def transaction(self, tenant):
        with self.engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(tenant)}
            )
            yield conn

    @staticmethod
    def scope(table, tenant):
        return table.c.tenant_id == tenant

    def seal(self, tenant, payload, purpose):
        return self.cipher.encrypt(tenant, json.dumps(payload).encode(), purpose)

    def unseal(self, tenant, payload, purpose):
        return json.loads(self.cipher.decrypt(tenant, payload, purpose))

    def document(self, tenant, doc_id, conn=None):
        query = select(documents).where(self.scope(documents, tenant), documents.c.id == doc_id)
        if conn is not None:
            row = conn.execute(query).mappings().first()
        else:
            with self.transaction(tenant) as c:
                row = c.execute(query).mappings().first()
        if not row:
            raise AppError("not_found", "Document not found", 404)
        return dict(row)

    def create_document(self, tenant, doc_id, upload_key, digest):
        with self.transaction(tenant) as conn:
            self.admit(conn, tenant)
            created = conn.execute(
                pg_insert(documents)
                .values(
                    tenant_id=tenant,
                    id=doc_id,
                    upload_key=upload_key,
                    digest=digest,
                    status="queued",
                )
                .on_conflict_do_nothing(index_elements=["tenant_id", "upload_key"])
                .returning(documents.c.id)
            ).scalar_one_or_none()
            if created:
                job_id = uuid4()
                conn.execute(
                    insert(jobs).values(
                        tenant_id=tenant,
                        id=job_id,
                        document_id=doc_id,
                        kind="parse",
                        status="queued",
                        request_hash=digest,
                    )
                )
                return doc_id, True
            existing = (
                conn.execute(
                    select(documents).where(
                        self.scope(documents, tenant), documents.c.upload_key == upload_key
                    )
                )
                .mappings()
                .one()
            )
            if existing["digest"] != digest:
                raise AppError("idempotency_conflict", "Upload key has different content", 409)
            return existing["id"], False

    def enqueue_review(self, tenant, doc_id, review, fingerprint=None):
        payload = review.model_dump(mode="json")
        reviewed_hash = hashlib.sha256(review.parsed.model_dump_json().encode()).hexdigest()
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.transaction(tenant) as conn:
            row = (
                conn.execute(
                    select(documents)
                    .where(self.scope(documents, tenant), documents.c.id == doc_id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if not row:
                raise AppError("not_found", "Document not found", 404)
            if row["reviewed_hash"] and row["reviewed_hash"] != reviewed_hash:
                raise AppError(
                    "immutable_evidence", "Upload a new version to change reviewed evidence", 409
                )
            existing = conn.execute(
                select(jobs.c.id)
                .where(
                    self.scope(jobs, tenant),
                    jobs.c.document_id == doc_id,
                    jobs.c.kind == "index",
                    jobs.c.request_hash == request_hash,
                )
                .order_by(jobs.c.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            same_review = (
                row["parsed"] is not None
                and row["config"] == payload["settings"]
                and self.unseal(tenant, row["parsed"], str(doc_id)) == payload["parsed"]
            )
            if (
                existing
                and same_review
                and row["status"] in {"ready", "indexing"}
                and (row["status"] == "indexing" or row["embedding_fingerprint"] == fingerprint)
            ):
                return existing
            if row["status"] not in {"review", "ready", "failed"} or row["parsed"] is None:
                raise AppError("busy", "Document is not available for review", 409)
            active = conn.execute(
                select(jobs.c.id)
                .where(
                    self.scope(jobs, tenant),
                    jobs.c.document_id == doc_id,
                    jobs.c.kind == "compare",
                    jobs.c.status.in_(["queued", "running"]),
                )
                .limit(1)
            ).scalar_one_or_none()
            if active:
                raise AppError("busy", "Wait for active comparisons before changing the index", 409)
            current = ParsedDocument.model_validate(self.unseal(tenant, row["parsed"], str(doc_id)))
            if row["status"] == "ready" and current != review.parsed:
                raise AppError(
                    "immutable_evidence",
                    "Upload a new document version to change reviewed evidence",
                    409,
                )
            if len(current.pages) != len(review.parsed.pages):
                raise AppError("invalid_review", "Review must retain the original page count")
            job_id = uuid4()
            conn.execute(
                update(documents)
                .where(self.scope(documents, tenant), documents.c.id == doc_id)
                .values(
                    status="indexing",
                    reviewed_hash=reviewed_hash,
                    error_code=None,
                    parsed=self.seal(tenant, payload["parsed"], str(doc_id)),
                    config=payload["settings"],
                )
            )
            conn.execute(
                insert(jobs).values(
                    tenant_id=tenant,
                    id=job_id,
                    document_id=doc_id,
                    kind="index",
                    status="queued",
                    request_hash=request_hash,
                )
            )
            return job_id

    def enqueue_question(self, tenant, doc_id, request):
        payload = request.model_dump(mode="json")
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.transaction(tenant) as conn:
            self.admit(conn, tenant)
            # Shared lock prevents a simultaneous review changing the indexed document.
            row = (
                conn.execute(
                    select(documents)
                    .where(self.scope(documents, tenant), documents.c.id == doc_id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if not row:
                raise AppError("not_found", "Document not found", 404)
            if row["status"] != "ready":
                raise AppError("not_ready", "Review and index the document first", 409)
            existing = (
                conn.execute(
                    select(jobs).where(self.scope(jobs, tenant), jobs.c.id == request.run_id)
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["request_hash"] != digest or existing["document_id"] != doc_id:
                    raise AppError("idempotency_conflict", "Run ID has different input", 409)
                return request.run_id
            conn.execute(
                insert(jobs).values(
                    tenant_id=tenant,
                    id=request.run_id,
                    document_id=doc_id,
                    kind="compare",
                    status="queued",
                    request_hash=digest,
                    payload=self.seal(tenant, payload, str(request.run_id)),
                )
            )
            return request.run_id

    @staticmethod
    def admit(conn, tenant):
        # Distributed per-tenant admission, independent of API replica count.
        conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": tenant.int % (2**63 - 1)})
        pending = conn.execute(
            select(func.count())
            .select_from(jobs)
            .where(jobs.c.tenant_id == tenant, jobs.c.status.in_(["queued", "running"]))
        ).scalar_one()
        if pending >= 20:
            raise AppError("queue_quota", "Tenant already has 20 pending tasks", 429)

    def job(self, tenant, job_id):
        with self.transaction(tenant) as conn:
            row = (
                conn.execute(select(jobs).where(self.scope(jobs, tenant), jobs.c.id == job_id))
                .mappings()
                .first()
            )
        if not row:
            raise AppError("not_found", "Job not found", 404)
        return dict(row)

    def claim(self, tenant, lease_seconds, job_id=None):
        token = uuid4()
        with self.transaction(tenant) as conn:
            row = (
                conn.execute(
                    select(jobs)
                    .where(
                        self.scope(jobs, tenant),
                        jobs.c.attempts < 3,
                        jobs.c.id == job_id if job_id else text("true"),
                        (
                            (jobs.c.status == "queued")
                            | ((jobs.c.status == "running") & (jobs.c.lease_until < func.now()))
                        ),
                    )
                    .order_by(jobs.c.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            conn.execute(
                update(jobs)
                .where(self.scope(jobs, tenant), jobs.c.id == row["id"])
                .values(
                    status="running",
                    attempts=jobs.c.attempts + 1,
                    lease_token=token,
                    lease_until=func.now() + text(f"interval '{int(lease_seconds)} seconds'"),
                )
            )
            return {**row, "lease_token": token, "attempts": row["attempts"] + 1}

    def heartbeat(self, tenant, job_id, token, seconds):
        with self.transaction(tenant) as conn:
            return (
                conn.execute(
                    update(jobs)
                    .where(
                        self.scope(jobs, tenant),
                        jobs.c.id == job_id,
                        jobs.c.status == "running",
                        jobs.c.lease_token == token,
                        jobs.c.lease_until > func.now(),
                    )
                    .values(lease_until=func.now() + text(f"interval '{int(seconds)} seconds'"))
                ).rowcount
                == 1
            )

    @contextmanager
    def finish(self, tenant, job, outcome="completed"):
        with self.transaction(tenant) as conn:
            owned = conn.execute(
                select(jobs.c.id)
                .where(
                    self.scope(jobs, tenant),
                    jobs.c.id == job["id"],
                    jobs.c.status == "running",
                    jobs.c.lease_token == job["lease_token"],
                    jobs.c.lease_until > func.now(),
                )
                .with_for_update()
            ).scalar_one_or_none()
            if owned is None:
                raise AppError("lease_lost", "Worker no longer owns this task", 409)
            yield conn
            conn.execute(
                update(jobs)
                .where(self.scope(jobs, tenant), jobs.c.id == job["id"])
                .values(status=outcome, lease_until=None, lease_token=None)
            )

    def fail(self, tenant, job, code):
        with self.finish(tenant, job, outcome="failed") as conn:
            conn.execute(
                update(jobs)
                .where(self.scope(jobs, tenant), jobs.c.id == job["id"])
                .values(error_code=code)
            )
            if job["kind"] != "compare":
                conn.execute(
                    update(documents)
                    .where(self.scope(documents, tenant), documents.c.id == job["document_id"])
                    .values(status="failed", error_code=code)
                )

    def retry(self, tenant, job, *, capacity_wait=False):
        with self.finish(tenant, job, outcome="queued") as conn:
            conn.execute(
                update(jobs)
                .where(self.scope(jobs, tenant), jobs.c.id == job["id"])
                .values(
                    dispatched_at=func.now(),
                    error_code="parser_busy" if capacity_wait else "retry_scheduled",
                    attempts=jobs.c.attempts - 1 if capacity_wait else jobs.c.attempts,
                )
            )

    def dispatchable(self, tenant):
        with self.transaction(tenant) as conn:
            return list(
                conn.execute(
                    select(jobs.c.id)
                    .where(
                        self.scope(jobs, tenant),
                        jobs.c.attempts < 3,
                        (
                            (jobs.c.status == "queued")
                            | ((jobs.c.status == "running") & (jobs.c.lease_until < func.now()))
                        ),
                        (
                            (jobs.c.dispatched_at.is_(None))
                            | (jobs.c.dispatched_at < func.now() - text("interval '30 seconds'"))
                        ),
                    )
                    .order_by(jobs.c.created_at)
                    .limit(100)
                ).scalars()
            )

    def mark_dispatched(self, tenant, job_id):
        with self.transaction(tenant) as conn:
            conn.execute(
                update(jobs)
                .where(self.scope(jobs, tenant), jobs.c.id == job_id)
                .values(dispatched_at=func.now())
            )

    def save_parsed(self, tenant, job, parsed):
        with self.finish(tenant, job) as conn:
            conn.execute(
                update(documents)
                .where(self.scope(documents, tenant), documents.c.id == job["document_id"])
                .values(
                    status="review",
                    parsed=self.seal(
                        tenant, parsed.model_dump(mode="json"), str(job["document_id"])
                    ),
                )
            )

    def cached_embedding(self, tenant, key):
        with self.transaction(tenant) as conn:
            return conn.execute(
                select(embedding_cache.c.embedding).where(
                    self.scope(embedding_cache, tenant), embedding_cache.c.key == key
                )
            ).scalar_one_or_none()

    def cache_embedding(self, tenant, key, vector, job, token_count):
        with self.transaction(tenant) as conn:
            owned = conn.execute(
                select(jobs.c.id)
                .where(
                    self.scope(jobs, tenant),
                    jobs.c.id == job["id"],
                    jobs.c.lease_token == job["lease_token"],
                    jobs.c.status == "running",
                    jobs.c.lease_until > func.now(),
                )
                .with_for_update()
            ).scalar_one_or_none()
            if owned is None:
                raise AppError("lease_lost", "Worker no longer owns this task", 409)
            conn.execute(
                pg_insert(embedding_cache)
                .values(tenant_id=tenant, key=key, embedding=vector)
                .on_conflict_do_nothing()
            )
            conn.execute(
                update(documents)
                .where(self.scope(documents, tenant), documents.c.id == job["document_id"])
                .values(indexing_tokens=documents.c.indexing_tokens + token_count)
            )

    def save_index(self, tenant, job, indexed, token_count, duration, fingerprint):
        doc_id = job["document_id"]
        with self.finish(tenant, job) as conn:
            conn.execute(
                delete(chunks).where(self.scope(chunks, tenant), chunks.c.document_id == doc_id)
            )
            for chunk, vector in indexed:
                conn.execute(
                    insert(chunks).values(
                        tenant_id=tenant,
                        document_id=doc_id,
                        key=chunk.key,
                        page=chunk.page,
                        embedding=vector,
                        payload=self.seal(tenant, asdict(chunk), f"{doc_id}:{chunk.key}"),
                    )
                )
            conn.execute(
                update(documents)
                .where(self.scope(documents, tenant), documents.c.id == doc_id)
                .values(
                    status="ready",
                    indexing_ms=duration,
                    embedding_fingerprint=fingerprint,
                )
            )

    def retrieve(self, tenant, doc_id, vector, k):
        with self.transaction(tenant) as conn:
            rows = (
                conn.execute(
                    select(chunks)
                    .where(self.scope(chunks, tenant), chunks.c.document_id == doc_id)
                    .order_by(chunks.c.embedding.cosine_distance(vector), chunks.c.key)
                    .limit(k)
                )
                .mappings()
                .all()
            )
        return [Chunk(**self.unseal(tenant, r["payload"], f"{doc_id}:{r['key']}")) for r in rows]

    def save_comparison(self, tenant, job, comparison):
        with self.finish(tenant, job) as conn:
            conn.execute(
                update(jobs)
                .where(self.scope(jobs, tenant), jobs.c.id == job["id"])
                .values(
                    result=self.seal(tenant, comparison.model_dump(mode="json"), str(job["id"]))
                )
            )

    def list_documents(self, tenant):
        with self.transaction(tenant) as conn:
            return list(
                conn.execute(
                    select(documents.c.id, documents.c.status)
                    .where(self.scope(documents, tenant))
                    .order_by(documents.c.created_at.desc())
                    .limit(100)
                ).mappings()
            )

    def list_jobs(self, tenant):
        with self.transaction(tenant) as conn:
            return list(
                conn.execute(
                    select(
                        jobs.c.id,
                        jobs.c.status,
                        jobs.c.kind,
                        jobs.c.document_id,
                        jobs.c.attempts,
                        jobs.c.error_code,
                    )
                    .where(self.scope(jobs, tenant))
                    .order_by(jobs.c.created_at.desc())
                    .limit(100)
                ).mappings()
            )

    def delete_document(self, tenant, doc_id):
        with self.transaction(tenant) as conn:
            self.document(tenant, doc_id, conn)
            conn.execute(
                delete(documents).where(self.scope(documents, tenant), documents.c.id == doc_id)
            )
            # Conservative confidential-data policy: purge tenant embedding reuse on any deletion.
            conn.execute(delete(embedding_cache).where(self.scope(embedding_cache, tenant)))

    def reap(self, tenant):
        with self.transaction(tenant) as conn:
            expired = (
                conn.execute(
                    select(jobs)
                    .where(
                        self.scope(jobs, tenant),
                        jobs.c.status == "running",
                        jobs.c.attempts >= 3,
                        jobs.c.lease_until < func.now(),
                    )
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            for job in expired:
                conn.execute(
                    update(jobs)
                    .where(self.scope(jobs, tenant), jobs.c.id == job["id"])
                    .values(status="dead", error_code="attempts_exhausted")
                )
                if job["kind"] != "compare":
                    conn.execute(
                        update(documents)
                        .where(self.scope(documents, tenant), documents.c.id == job["document_id"])
                        .values(status="failed", error_code="attempts_exhausted")
                    )
