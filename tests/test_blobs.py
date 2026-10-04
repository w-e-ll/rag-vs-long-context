import asyncio
from uuid import uuid4

import pytest

from rag_lab.core.errors import AppError
from rag_lab.ingestion.blobs import BlobStore


async def stream(data):
    for start in range(0, len(data), 7):
        yield data[start : start + 7]


def test_stream_roundtrip_and_truncation(tmp_path, cipher, tenant):
    store, doc = BlobStore(tmp_path, cipher), uuid4()
    data = b"%PDF-" + b"confidential content" * 100
    asyncio.run(store.upload(tenant, doc, stream(data), 10000))
    assert store.read(tenant, doc, 10000) == data
    path = store.path(tenant, doc)
    encrypted = path.read_bytes()
    assert b"confidential" not in encrypted
    path.write_bytes(encrypted[:-8])
    with pytest.raises(Exception):
        store.read(tenant, doc, 10000)


@pytest.mark.parametrize("data,limit", [(b"not a PDF", 100), (b"%PDF-" + b"a" * 100, 20)])
def test_upload_rejection_cleans_partial(tmp_path, cipher, tenant, data, limit):
    store, doc = BlobStore(tmp_path, cipher), uuid4()
    with pytest.raises(AppError):
        asyncio.run(store.upload(tenant, doc, stream(data), limit))
    assert not list(tmp_path.rglob("*.upload"))
    assert not list(tmp_path.rglob("*.blob"))
