"""Uploads are streamed; all expensive work is submitted as durable jobs."""

import time
from contextlib import asynccontextmanager
from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from rag_lab import __version__
from rag_lab.api.limits import BodyLimitMiddleware, throttle
from rag_lab.core.config import settings
from rag_lab.core.errors import AppError
from rag_lab.core.logging import configure, event, failure
from rag_lab.core.metrics import HTTP_TIME, REQUESTS
from rag_lab.core.models import (
    Comparison,
    DocumentView,
    JobView,
    ParsedDocument,
    Question,
    Resource,
    Review,
)
from rag_lab.core.providers import Provider
from rag_lab.core.security import Cipher, require_editor, resolve_identity
from rag_lab.db.repository import Repository
from rag_lab.ingestion.blobs import BlobStore

configure()


@asynccontextmanager
async def lifespan(app):
    settings()  # Fail closed before accepting requests when production settings are invalid.
    yield


app = FastAPI(
    title="RAG: When Is It Cheaper Than Long Context?", version=__version__, lifespan=lifespan
)
app.add_middleware(BodyLimitMiddleware)
bearer = HTTPBearer(auto_error=False)


@lru_cache
def repository():
    config = settings()
    return Repository(config.database_url, Cipher(config.encryption_key.get_secret_value()))


def identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise AppError("unauthorized", "A valid access token is required", 401)
    user = resolve_identity(credentials.credentials, settings().credentials_json.get_secret_value())
    throttle(user, settings().redis_url.get_secret_value())
    return user


def blob_store(repo):
    return BlobStore(settings().blob_dir, repo.cipher)


def error(request, code, message, status):
    return JSONResponse(
        {"code": code, "message": message, "request_id": getattr(request.state, "request_id", "")},
        status_code=status,
    )


@app.exception_handler(AppError)
async def app_error(request, exc):
    event("request.rejected", request_id=request.state.request_id, code=exc.code)
    return error(request, exc.code, exc.message, exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return error(request, "validation_error", "Request fields are invalid", 422)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    failure("database.error", exc, request_id=request.state.request_id)
    return error(request, "database_unavailable", "Database is temporarily unavailable", 503)


@app.middleware("http")
async def request_context(request, call_next):
    request.state.request_id = str(uuid4())
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        failure("request.unhandled", exc, request_id=request.state.request_id)
        response = error(request, "internal_error", "Request could not be completed", 500)
    route = getattr(request.scope.get("route"), "path", "unmatched")
    duration = time.perf_counter() - start
    REQUESTS.labels(route, str(response.status_code)).inc()
    HTTP_TIME.labels(route).observe(duration)
    event(
        "http.request",
        request_id=request.state.request_id,
        status=response.status_code,
        duration_ms=round(duration * 1000, 2),
    )
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/health/db")
def database_health(repo=Depends(repository)):
    with repo.engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/v1/documents", response_model=list[Resource])
def list_documents(user=Depends(identity), repo=Depends(repository)):
    return repo.list_documents(user.tenant_id)


@app.post("/api/v1/documents", response_model=Resource, status_code=202)
async def upload(
    request: Request,
    idempotency_key: UUID = Header(),
    user=Depends(identity),
    repo=Depends(repository),
):
    require_editor(user)
    if request.headers.get("content-type", "").split(";")[0] != "application/pdf":
        raise AppError("media_type", "Send PDF bytes as application/pdf", 415)
    doc_id = uuid4()
    blobs = blob_store(repo)
    digest = await blobs.upload(
        user.tenant_id, doc_id, request.stream(), settings().max_upload_bytes
    )
    try:
        selected, created = await run_in_threadpool(
            repo.create_document, user.tenant_id, doc_id, str(idempotency_key), digest
        )
    except Exception:
        blobs.delete(user.tenant_id, doc_id)
        raise
    if not created:
        blobs.delete(user.tenant_id, doc_id)
    row = await run_in_threadpool(repo.document, user.tenant_id, selected)
    event("upload.accepted", tenant_id=user.tenant_id, document_id=selected)
    return Resource(id=selected, status=row["status"])


@app.get("/api/v1/documents/{doc_id}", response_model=DocumentView)
def document(doc_id: UUID, user=Depends(identity), repo=Depends(repository)):
    row = repo.document(user.tenant_id, doc_id)
    parsed = (
        ParsedDocument.model_validate(repo.unseal(user.tenant_id, row["parsed"], str(doc_id)))
        if row["parsed"]
        else None
    )
    return DocumentView(
        id=doc_id,
        status=row["status"],
        parsed=parsed,
        settings=row["config"],
        indexing_tokens=row["indexing_tokens"],
        error_code=row["error_code"],
    )


@app.post("/api/v1/documents/{doc_id}/review", response_model=Resource, status_code=202)
def review(doc_id: UUID, body: Review, user=Depends(identity), repo=Depends(repository)):
    require_editor(user)
    job = repo.enqueue_review(user.tenant_id, doc_id, body, Provider(settings()).fingerprint)
    event("document.reviewed", tenant_id=user.tenant_id, document_id=doc_id, job_id=job)
    return Resource(id=job, status=repo.job(user.tenant_id, job)["status"])


@app.post("/api/v1/documents/{doc_id}/compare", response_model=Resource, status_code=202)
def compare(doc_id: UUID, body: Question, user=Depends(identity), repo=Depends(repository)):
    require_editor(user)
    job = repo.enqueue_question(user.tenant_id, doc_id, body)
    return Resource(id=job, status=repo.job(user.tenant_id, job)["status"])


@app.get("/api/v1/jobs", response_model=list[JobView])
def list_jobs(user=Depends(identity), repo=Depends(repository)):
    return repo.list_jobs(user.tenant_id)


@app.get("/api/v1/jobs/{job_id}", response_model=JobView)
def job(job_id: UUID, user=Depends(identity), repo=Depends(repository)):
    row = repo.job(user.tenant_id, job_id)
    return JobView(**{key: row[key] for key in JobView.model_fields})


@app.get("/api/v1/runs/{run_id}", response_model=Comparison)
def result(run_id: UUID, user=Depends(identity), repo=Depends(repository)):
    row = repo.job(user.tenant_id, run_id)
    if row["result"] is None:
        raise AppError("not_ready", "Experiment has no completed result", 409)
    return Comparison.model_validate(repo.unseal(user.tenant_id, row["result"], str(run_id)))


@app.delete("/api/v1/documents/{doc_id}", response_model=Resource)
def delete_document(doc_id: UUID, user=Depends(identity), repo=Depends(repository)):
    require_editor(user)
    repo.delete_document(user.tenant_id, doc_id)
    blob_store(repo).delete(user.tenant_id, doc_id)
    event("document.deleted", tenant_id=user.tenant_id, document_id=doc_id)
    return Resource(id=doc_id, status="deleted")


def main():
    import uvicorn
    from prometheus_client import start_http_server

    start_http_server(9100)
    uvicorn.run(app, host="0.0.0.0", port=8003, access_log=False)


if __name__ == "__main__":
    main()
