#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_password="$APP_DB_PASSWORD" -v migrator_password="$MIGRATOR_DB_PASSWORD" <<'SQL'
CREATE ROLE rag_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOBYPASSRLS;
CREATE ROLE rag_migrator LOGIN PASSWORD :'migrator_password' NOSUPERUSER NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO rag_app;
GRANT USAGE, CREATE ON SCHEMA public TO rag_migrator;
CREATE EXTENSION IF NOT EXISTS vector;
SQL
