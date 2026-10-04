"""Private parser service. No DB/key mounts, no outbound network, no access logs."""

import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import threading

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from rag_lab.core.logging import configure, event
from rag_lab.core.models import ParsedDocument
from rag_lab.ingestion.budgets import PARSER_HARD_SECONDS
from rag_lab.ingestion.errors import PARSER_ERRORS

configure()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
SLOTS = threading.BoundedSemaphore(1)
RUNNING = set()


async def reserved_extraction(raw):
    try:
        return await run_in_threadpool(extract, raw, slot_reserved=True)
    finally:
        SLOTS.release()


def extraction_finished(task):
    RUNNING.discard(task)
    if not task.cancelled() and task.exception() is not None:
        event("parser.failed", code="extraction_failed")


def extract(raw, *, slot_reserved=False):
    if not slot_reserved and not SLOTS.acquire(blocking=False):
        return JSONResponse({"error": "parser_busy"}, status_code=429)
    try:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.getcwd(),
            "TMPDIR": "/tmp",
            "TEMP": os.environ.get("TEMP", "/tmp"),
            "PDF_VISION_MODEL": os.environ.get("PDF_VISION_MODEL", ""),
            "OMP_THREAD_LIMIT": "1",
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "rag_lab.ingestion.extract"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=sys.platform != "win32",
        )
        try:
            output, _ = process.communicate(raw, timeout=PARSER_HARD_SECONDS)
        except subprocess.TimeoutExpired:
            if sys.platform != "win32":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.communicate()
            event("parser.failed", code="parser_timeout")
            return JSONResponse({"error": "parser_timeout"}, status_code=422)
        if process.returncode:
            code = "parser_process_stopped" if process.returncode < 0 else "extraction_failed"
            if process.returncode in {-24, -25}:
                code = "parser_resource_limit"
            if 0 < len(output) < 1000:
                try:
                    body = json.loads(output)
                    reported = body.get("error") if isinstance(body, dict) else None
                    if isinstance(reported, str) and reported in PARSER_ERRORS:
                        code = reported
                except ValueError:
                    pass
            event("parser.failed", code=code, status=process.returncode)
            return JSONResponse({"error": code}, status_code=422)
        return ParsedDocument.model_validate_json(output)
    finally:
        if not slot_reserved:
            SLOTS.release()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    executable = shutil.which("tesseract")
    if executable:
        try:
            probe = subprocess.run(
                [executable, "--list-langs"], capture_output=True, timeout=5, check=False
            )
            if probe.returncode == 0 and b"eng" in probe.stdout.splitlines():
                return {"status": "ready", "ocr_language": "eng"}
        except (OSError, subprocess.SubprocessError):
            pass
    return JSONResponse({"status": "not_ready", "code": "ocr_unavailable"}, status_code=503)


@app.post("/parse", response_model=ParsedDocument)
async def parse(request: Request):
    if not SLOTS.acquire(blocking=False):
        return JSONResponse({"error": "parser_busy"}, status_code=429)
    transferred = False
    try:
        data = bytearray()
        try:
            async with asyncio.timeout(30):
                async for block in request.stream():
                    if len(data) + len(block) > 20000000:
                        return JSONResponse({"error": "too_large"}, status_code=413)
                    data.extend(block)
        except TimeoutError:
            return JSONResponse({"error": "upload_timeout"}, status_code=408)
        task = asyncio.create_task(reserved_extraction(bytes(data)))
        RUNNING.add(task)
        task.add_done_callback(extraction_finished)
        transferred = True
        # Client cancellation must not release capacity while the child is still running.
        return await asyncio.shield(task)
    finally:
        if not transferred:
            SLOTS.release()
