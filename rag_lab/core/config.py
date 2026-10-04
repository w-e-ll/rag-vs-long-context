"""Operator configuration; no provider URL or tenant is accepted from a request."""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from rag_lab.core.security import Cipher, credential_record

DIMENSIONS = 768


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    deployment_mode: Literal["development", "production"] = "development"
    database_url: str = "postgresql+psycopg://rag_app:local@localhost:5436/rag_lab"
    credentials_json: SecretStr = SecretStr("{}")
    encryption_key: SecretStr = SecretStr("")
    blob_dir: Path = Path("var/blobs")
    parser_url: str = "http://parser:8010"
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    provider_mode: Literal["demo", "ollama"] = "demo"
    ollama_url: str = "http://ollama:11434"
    llm_model: str = "llama3.2:3b"
    embedding_model: str = "nomic-embed-text"
    llm_context_tokens: int = Field(default=8192, ge=2048, le=65536)
    max_upload_bytes: int = Field(default=20000000, ge=1000, le=50000000)
    max_document_tokens: int = Field(default=16000, ge=1000, le=60000)
    lease_seconds: int = Field(default=120, ge=30)
    worker_poll_seconds: float = 2

    @model_validator(mode="after")
    def local_endpoints(self):
        for url in (self.ollama_url, self.parser_url):
            parsed = urlparse(url)
            if (
                parsed.scheme != "http"
                or parsed.hostname
                not in {"localhost", "127.0.0.1", "ollama", "parser", "host.docker.internal"}
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Only approved local service endpoints are supported")
        if self.deployment_mode == "production":
            if self.provider_mode != "ollama":
                raise ValueError("Production requires a real local model provider")
            try:
                Cipher(self.encryption_key.get_secret_value())
                registry = json.loads(self.credentials_json.get_secret_value())
                if not isinstance(registry, dict) or not registry:
                    raise ValueError()
                active = 0
                for digest, record in registry.items():
                    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                        raise ValueError()
                    active += credential_record(record, require_expiry=True) is not None
                if not active:
                    raise ValueError()
            except Exception as exc:
                raise ValueError(
                    "Production needs a valid key and active expiring credentials"
                ) from exc
        return self


@lru_cache
def settings() -> Settings:
    # No confidential prompts in third-party tracing, including inherited settings.
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    return Settings()
