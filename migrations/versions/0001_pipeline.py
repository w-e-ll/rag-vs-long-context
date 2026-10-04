"""Tenant-isolated artifacts, leased jobs and vectors."""

from alembic import op

from rag_lab.db.schema import metadata

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    metadata.create_all(op.get_bind())
    for table in metadata.sorted_tables:
        name = table.name
        op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
        op.execute(f'''CREATE POLICY tenant_scope ON "{name}"
            USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)''')
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{name}" TO rag_app')
    op.execute("CREATE INDEX job_delivery ON jobs (tenant_id, status, created_at)")


def downgrade():
    raise RuntimeError("Destructive downgrade is intentionally disabled; restore a verified backup")
