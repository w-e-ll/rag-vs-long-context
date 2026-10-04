# Sunday AI Builds 03
Read README.md, DECISIONS.md and docs/security.md before changes.
Use Python 3.13 and uv; keep uv.lock. Preserve .venv and .env.
Keep HTTP/UI, core computations, persistence and untrusted PDF processing separate.
Tenant identity comes from server-managed credentials, never request metadata.
Every document, job, chunk and experiment operation must be tenant-scoped.
Use SQL filters and PostgreSQL FORCE RLS with a non-owner runtime role.
Queue delivery is at-least-once. Fence writes with a lease token. No DB locks over inference.
No external AI calls or tracing for confidential documents without explicit authorization.
Never log document text, filenames, questions, answers, tokens, credentials or DSNs.
Money uses Decimal. Report simulated/model-reported usage and estimates separately.
Tests: uv run pytest -q; uv run ruff check .; uv run ruff format --check .
Use a separate *_test database for integration tests. Never delete data volumes to fix startup.
Keep docs honest about untested checks and production gaps.
