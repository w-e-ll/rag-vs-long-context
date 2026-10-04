"""Create local demo secrets once, without printing credentials or replacing existing files."""

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path
from uuid import uuid4


def main():
    root = Path(__file__).resolve().parents[1]
    env, credentials = root / ".env", root / ".demo-credentials.json"
    if env.exists() or credentials.exists():
        raise SystemExit(
            "Setup files already exist; preserved. Inspect them manually if incomplete."
        )
    registry, local = {}, {}
    for name in ("alpha", "beta"):
        token, tenant = secrets.token_urlsafe(36), str(uuid4())
        local[name] = {"token": token, "tenant_id": tenant}
        registry[hashlib.sha256(token.encode()).hexdigest()] = {
            "tenant_id": tenant,
            "user_id": name + "-editor",
            "role": "editor",
        }
    config = {
        name: secrets.token_urlsafe(32)
        for name in (
            "POSTGRES_PASSWORD",
            "APP_DB_PASSWORD",
            "MIGRATOR_DB_PASSWORD",
            "REDIS_PASSWORD",
            "GRAFANA_PASSWORD",
        )
    }
    config.update(
        ENCRYPTION_KEY=base64.b64encode(os.urandom(32)).decode(),
        CREDENTIALS_JSON=json.dumps(registry, separators=(",", ":")),
        PROVIDER_MODE="demo",
        LLM_MODEL="llama3.2:3b",
        EMBEDDING_MODEL="nomic-embed-text",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
    )
    with env.open("x", encoding="utf-8") as output:
        output.write("\n".join(f"{k}='{v}'" for k, v in config.items()) + "\n")
    with credentials.open("x", encoding="utf-8") as output:
        json.dump(local, output, indent=2)
    os.chmod(env, 0o600)
    os.chmod(credentials, 0o600)
    print("Created .env and .demo-credentials.json. Keep both private; do not commit them.")


if __name__ == "__main__":
    main()
