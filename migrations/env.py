"""Use MIGRATION_DATABASE_URL for DDL; runtime credentials cannot own tables."""

import os

from alembic import context
from sqlalchemy import create_engine

from rag_lab.db.schema import metadata

engine = create_engine(os.environ["MIGRATION_DATABASE_URL"], hide_parameters=True)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
