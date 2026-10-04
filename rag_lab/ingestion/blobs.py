"""Encrypted streaming blob adapter for a shared Docker volume.

Objects are random UUIDs. Multi-host deployments must supply shared object storage.
Each frame and the final frame count are authenticated; truncated uploads cannot be read.
"""

import hashlib
import os
import struct
from pathlib import Path

from rag_lab.core.errors import AppError


class BlobStore:
    def __init__(self, root: Path, cipher):
        self.root, self.cipher = root, cipher

    def path(self, tenant, doc_id):
        return self.root / str(tenant) / f"{doc_id}.blob"

    async def upload(self, tenant, doc_id, stream, max_bytes):
        path = self.path(tenant, doc_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".upload")
        digest, total, count, prefix = hashlib.sha256(), 0, 0, b""
        try:
            with temp.open("xb") as output:
                output.write(b"RAGB1")
                async for incoming in stream:
                    total += len(incoming)
                    if total > max_bytes:
                        raise AppError("too_large", "PDF exceeds upload limit", 413)
                    prefix = (prefix + incoming)[:5]
                    digest.update(incoming)
                    for offset in range(0, len(incoming), 65536):
                        frame = self.cipher.encrypt(
                            tenant, incoming[offset : offset + 65536], f"{doc_id}:{count}"
                        )
                        output.write(struct.pack(">I", len(frame)) + frame)
                        count += 1
                if prefix != b"%PDF-":
                    raise AppError("not_pdf", "A PDF file is required")
                final = self.cipher.encrypt(tenant, str(count).encode(), f"{doc_id}:final")
                output.write(struct.pack(">I", 0) + final)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp, path)
            return digest.hexdigest()
        finally:
            temp.unlink(missing_ok=True)

    def read(self, tenant, doc_id, limit):
        result, count = bytearray(), 0
        with self.path(tenant, doc_id).open("rb") as source:
            if source.read(5) != b"RAGB1":
                raise ValueError("Invalid encrypted object")
            while True:
                header = source.read(4)
                if len(header) != 4:
                    raise ValueError("Truncated encrypted object")
                size = struct.unpack(">I", header)[0]
                if size == 0:
                    footer = source.read(100)
                    expected = self.cipher.decrypt(tenant, footer, f"{doc_id}:final")
                    if expected != str(count).encode() or source.read(1):
                        raise ValueError("Invalid object footer")
                    return bytes(result)
                if size > 65564:
                    raise ValueError("Invalid frame size")
                result.extend(self.cipher.decrypt(tenant, source.read(size), f"{doc_id}:{count}"))
                if len(result) > limit:
                    raise ValueError("Object exceeds limit")
                count += 1

    def delete(self, tenant, doc_id):
        self.path(tenant, doc_id).unlink(missing_ok=True)
