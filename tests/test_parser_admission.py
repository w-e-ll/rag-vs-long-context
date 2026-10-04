import asyncio
import threading
from types import SimpleNamespace

import pytest

from rag_lab.ingestion import server


class Stream:
    def __init__(self, blocks=(), failure=None):
        self.blocks, self.failure, self.read = blocks, failure, False

    async def stream(self):
        self.read = True
        for block in self.blocks:
            yield block
        if self.failure:
            raise self.failure


@pytest.fixture
def slot(monkeypatch):
    slot = threading.BoundedSemaphore(1)
    monkeypatch.setattr(server, "SLOTS", slot)
    return slot


def test_busy_parser_rejects_before_reading_request(slot):
    assert slot.acquire(False)
    request = Stream([b"sensitive PDF"])
    response = asyncio.run(server.parse(request))
    assert response.status_code == 429
    assert not request.read
    slot.release()


def test_upload_limit_releases_slot_without_extraction(slot, monkeypatch):
    monkeypatch.setattr(server, "extract", lambda *a, **k: pytest.fail("Must not parse"))
    response = asyncio.run(server.parse(Stream([b"x" * 20000001])))
    assert response.status_code == 413
    assert slot.acquire(False)
    slot.release()


@pytest.mark.parametrize("failure", [RuntimeError("private"), TimeoutError()])
def test_failed_upload_releases_slot(slot, failure):
    if isinstance(failure, TimeoutError):
        assert asyncio.run(server.parse(Stream(failure=failure))).status_code == 408
    else:
        with pytest.raises(RuntimeError):
            asyncio.run(server.parse(Stream(failure=failure)))
    assert slot.acquire(False)
    slot.release()


def test_slot_is_held_through_extraction(slot, monkeypatch):
    def extract(raw, *, slot_reserved):
        assert raw == b"%PDF-test" and slot_reserved
        assert not slot.acquire(False)
        return {"done": True}

    monkeypatch.setattr(server, "extract", extract)
    assert asyncio.run(server.parse(Stream([b"%PDF-test"]))) == {"done": True}
    assert slot.acquire(False)
    slot.release()


def test_cancelled_client_does_not_release_running_parser(slot, monkeypatch):
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()

        async def in_thread(*args, **kwargs):
            started.set()
            await finish.wait()
            return {"done": True}

        monkeypatch.setattr(server, "run_in_threadpool", in_thread)
        request = asyncio.create_task(server.parse(Stream([b"%PDF-test"])))
        await started.wait()
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert not slot.acquire(False)
        pending = list(server.RUNNING)
        finish.set()
        await asyncio.gather(*pending)
        assert slot.acquire(False)
        slot.release()

    asyncio.run(scenario())


def test_readiness_requires_english_ocr(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda _: "tesseract")
    monkeypatch.setattr(
        server.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"Languages:\neng\nosd\n"),
    )
    assert server.ready()["status"] == "ready"
    monkeypatch.setattr(
        server.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"Languages:\nosd\n"),
    )
    assert server.ready().status_code == 503


def test_readiness_does_not_expose_runtime_errors(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda _: "tesseract")

    def failed(*a, **k):
        raise OSError("PRIVATE PATH AND CONFIG")

    monkeypatch.setattr(server.subprocess, "run", failed)
    response = server.ready()
    assert response.status_code == 503 and b"PRIVATE" not in response.body
