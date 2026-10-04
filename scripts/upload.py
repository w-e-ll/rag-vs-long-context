"""Stream an upload from disk without loading the entire PDF into client memory."""

import argparse
import getpass
from pathlib import Path
from uuid import UUID, uuid4

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--key", type=UUID, help="Reuse this UUID when retrying the same upload")
    args = parser.parse_args()
    key = args.key or uuid4()
    print("Upload idempotency key:", key)
    token = getpass.getpass("Tenant access token: ")
    with args.pdf.open("rb") as source, httpx.Client(timeout=90, trust_env=False) as client:
        result = client.post(
            "http://127.0.0.1:8003/api/v1/documents",
            content=source,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/pdf",
                "Idempotency-Key": str(key),
            },
        )
    result.raise_for_status()
    print(result.json())


if __name__ == "__main__":
    main()
