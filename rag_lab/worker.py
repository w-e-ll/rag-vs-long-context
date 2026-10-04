"""Stateless consumers; leases are renewed while expensive work runs outside transactions."""

import hashlib
import json
import threading
import time
from uuid import UUID

import httpx
from prometheus_client import start_http_server

from rag_lab.core.chunking import chunk_document, tokens
from rag_lab.core.config import settings
from rag_lab.core.errors import AppError
from rag_lab.core.experiment import compare
from rag_lab.core.logging import configure, event, failure
from rag_lab.core.metrics import (
    JOBS,
    PDF_PAGES,
    PDF_VISION,
    PDF_VISION_TIME,
    PDF_VISION_TOKENS,
    REUSED,
    STAGE_TIME,
)
from rag_lab.core.models import ChunkSettings, ParsedDocument
from rag_lab.core.providers import Provider
from rag_lab.core.security import Cipher
from rag_lab.db.repository import Repository
from rag_lab.ingestion.blobs import BlobStore
from rag_lab.ingestion.budgets import PARSER_CLIENT_SECONDS
from rag_lab.ingestion.errors import check_parser_response
from rag_lab.queue import GROUP, STREAM, client


def execute(repo, blobs, tenant, job, provider):
    config = provider.config
    if job["kind"] == "parse":
        raw = blobs.read(tenant, job["document_id"], config.max_upload_bytes)
        with httpx.Client(timeout=PARSER_CLIENT_SECONDS, trust_env=False) as client:
            response = client.post(
                config.parser_url + "/parse",
                content=raw,
                headers={"Content-Type": "application/pdf"},
            )
        check_parser_response(response)
        parsed = ParsedDocument.model_validate(response.json())
        for page in parsed.pages:
            PDF_PAGES.labels(page.method).inc()
            PDF_VISION.labels(page.vision_status).inc()
            if page.vision_ms:
                PDF_VISION_TIME.observe(page.vision_ms / 1000)
            PDF_VISION_TOKENS.labels("input").inc(page.vision_input_tokens)
            PDF_VISION_TOKENS.labels("output").inc(page.vision_output_tokens)
        repo.save_parsed(tenant, job, parsed)
    elif job["kind"] == "index":
        start = time.perf_counter()
        doc = repo.document(tenant, job["document_id"])
        parsed = ParsedDocument.model_validate(repo.unseal(tenant, doc["parsed"], str(doc["id"])))
        config_chunk = ChunkSettings.model_validate(doc["config"])
        indexed, new_tokens = [], 0
        for chunk in chunk_document(parsed, config_chunk):
            digest = hashlib.sha256((provider.fingerprint + "\0" + chunk.text).encode()).hexdigest()
            vector = repo.cached_embedding(tenant, digest)
            if vector is None:
                vector = provider.embed(chunk.text)
                repo.cache_embedding(tenant, digest, vector, job, tokens(chunk.text))
                new_tokens += tokens(chunk.text)
            else:
                REUSED.inc()
            indexed.append((chunk, vector))
        if not indexed:
            raise AppError("empty_document", "Document contains no indexable text")
        repo.save_index(
            tenant,
            job,
            indexed,
            doc["indexing_tokens"] + new_tokens,
            (time.perf_counter() - start) * 1000,
            provider.fingerprint,
        )
    else:
        repo.save_comparison(tenant, job, compare(repo, tenant, job, provider))


def run_one(repo, blobs, tenant, job, provider):
    stop = threading.Event()

    def renew():
        while not stop.wait(provider.config.lease_seconds / 3):
            try:
                if not repo.heartbeat(
                    tenant, job["id"], job["lease_token"], provider.config.lease_seconds
                ):
                    return
            except Exception as exc:
                failure("worker.heartbeat_failed", exc, job_id=job["id"])
                return

    heartbeat = threading.Thread(target=renew, daemon=True)
    heartbeat.start()
    event(
        "worker.started",
        tenant_id=tenant,
        job_id=job["id"],
        stage=job["kind"],
        attempt=job["attempts"],
    )
    try:
        with STAGE_TIME.labels(job["kind"]).time():
            execute(repo, blobs, tenant, job, provider)
        JOBS.labels(job["kind"], "completed").inc()
        event("worker.completed", job_id=job["id"])
    except Exception as exc:
        code = exc.code if isinstance(exc, AppError) else "processing_failed"
        if code == "parser_busy" and job["kind"] == "parse":
            try:
                repo.retry(tenant, job, capacity_wait=True)
                JOBS.labels(job["kind"], "deferred").inc()
                event("worker.deferred", job_id=job["id"], code=code)
            except Exception as save_exc:
                failure("worker.failure_save_failed", save_exc, job_id=job["id"])
            return
        failure("worker.failed", exc, job_id=job["id"], code=code)
        JOBS.labels(job["kind"], "failed").inc()
        try:
            transient = isinstance(exc, httpx.TransportError) or (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code in {429, 502, 503, 504}
            )
            if transient and job["attempts"] < 3:
                repo.retry(tenant, job)
            else:
                repo.fail(tenant, job, code)
        except Exception as save_exc:
            failure("worker.failure_save_failed", save_exc, job_id=job["id"])
    finally:
        stop.set()
        heartbeat.join(timeout=2)


def main():
    configure()
    config = settings()
    cipher = Cipher(config.encryption_key.get_secret_value())
    repo = Repository(config.database_url, cipher)
    blobs, provider = BlobStore(config.blob_dir, cipher), Provider(config)
    tenants = sorted(
        {
            UUID(v["tenant_id"])
            for v in json.loads(config.credentials_json.get_secret_value()).values()
        },
        key=str,
    )
    if not tenants:
        raise RuntimeError("Configure tenant credentials before starting workers")
    start_http_server(9101)
    from uuid import uuid4

    consumer = str(uuid4())
    while True:
        try:
            redis = client(config)
            claimed = redis.xautoclaim(
                STREAM,
                GROUP,
                consumer,
                min_idle_time=config.lease_seconds * 1000,
                start_id="0-0",
                count=1,
            )
            messages = claimed[1]
            if not messages:
                result = redis.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=1, block=5000)
                messages = result[0][1] if result else []
            for message_id, fields in messages:
                try:
                    tenant, job_id = UUID(fields["tenant_id"]), UUID(fields["job_id"])
                    if tenant in tenants:
                        job = repo.claim(tenant, config.lease_seconds, job_id)
                        if job:
                            run_one(repo, blobs, tenant, job, provider)
                    redis.xack(STREAM, GROUP, message_id)
                    redis.xdel(STREAM, message_id)
                except (ValueError, KeyError):
                    redis.xack(STREAM, GROUP, message_id)
                    event("queue.invalid_notification")
        except Exception as exc:
            failure("worker.poll_failed", exc)
            time.sleep(config.worker_poll_seconds)


if __name__ == "__main__":
    main()
