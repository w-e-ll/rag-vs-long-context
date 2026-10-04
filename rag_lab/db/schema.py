"""Schema declared explicitly; migrations own creation and grants."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()


def tenant_column():
    return Column("tenant_id", UUID(as_uuid=True), primary_key=True)


def now_column():
    return Column(
        "created_at", DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


documents = Table(
    "documents",
    metadata,
    tenant_column(),
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("upload_key", String(64), nullable=False),
    Column("digest", String(64), nullable=False),
    Column("reviewed_hash", String(64)),
    Column("status", String(32), nullable=False),
    Column("parsed", LargeBinary),
    Column("config", JSONB),
    Column("indexing_tokens", Integer, nullable=False, server_default="0"),
    Column("indexing_ms", Float, nullable=False, server_default="0"),
    Column("embedding_fingerprint", String(200)),
    Column("error_code", String(60)),
    now_column(),
    UniqueConstraint("tenant_id", "upload_key"),
)
chunks = Table(
    "chunks",
    metadata,
    tenant_column(),
    Column("document_id", UUID(as_uuid=True), primary_key=True),
    Column("key", String(120), primary_key=True),
    Column("page", Integer, nullable=False),
    Column("payload", LargeBinary, nullable=False),
    Column("embedding", Vector(768), nullable=False),
    ForeignKeyConstraint(
        ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"], ondelete="CASCADE"
    ),
)
embedding_cache = Table(
    "embedding_cache",
    metadata,
    tenant_column(),
    Column("key", String(64), primary_key=True),
    Column("embedding", Vector(768), nullable=False),
    now_column(),
)
jobs = Table(
    "jobs",
    metadata,
    tenant_column(),
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("kind", String(24), nullable=False),
    Column("status", String(24), nullable=False),
    Column("payload", LargeBinary),
    Column("result", LargeBinary),
    Column("request_hash", String(64), nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("lease_token", UUID(as_uuid=True)),
    Column("lease_until", DateTime(timezone=True)),
    Column("dispatched_at", DateTime(timezone=True)),
    Column("error_code", String(60)),
    now_column(),
    ForeignKeyConstraint(
        ["tenant_id", "document_id"], ["documents.tenant_id", "documents.id"], ondelete="CASCADE"
    ),
)
