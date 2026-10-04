# Project files

| File / directory | Purpose | Maintenance |
|---|---|---|
| pyproject.toml / uv.lock | Python 3.13 metadata and resolved dependencies | Change together with uv; no parallel requirements.txt |
| VERSION.txt / CHANGELOG.md | App version and release history | Keep API and package version aligned |
| AGENTS.md | Engineering and safety rules | Update when project standards change |
| rag_lab/core/models.py | Strict nested API and experiment contracts | Add validation with every new result/config field |
| rag_lab/core/config.py | Operator settings, local service allowlist, tracing disabled | Do not accept service URLs from document requests |
| rag_lab/core/chunking.py | LangChain splitting, token proxy and parent expansion | Version splitter changes and benchmark evidence coverage |
| rag_lab/core/providers.py | Demo embeddings/answers and private Ollama | Preserve usage labels, dimensions and model fingerprints |
| rag_lab/core/accounting.py | Decimal scenario prices and break-even | Test equal/negative savings, zero indexing and unknown quality |
| rag_lab/core/experiment.py | Paired experiment orchestration | Preserve same source/model, snapshots and limits |
| rag_lab/core/security.py | Credential resolution and tenant-bound encryption | Audit tenant/context handling and key rotation design |
| rag_lab/core/logging.py / metrics.py | Metadata-only events and Prometheus instruments | Keep labels bounded; never introduce sensitive payloads |
| rag_lab/db/schema.py | Typed PostgreSQL/pgvector tables | New changes need a new Alembic migration |
| rag_lab/db/repository.py | RLS-scoped transactions, outbox, lease fencing and reuse | Check concurrent claims, deletion and cross-tenant reads |
| rag_lab/api/main.py / limits.py | HTTP contracts, auth, streaming and quotas | Match API examples; test safe error responses |
| rag_lab/ingestion/blobs.py | Framed encrypted shared-volume objects | Preserve truncation detection and finalization semantics |
| rag_lab/ingestion/extract.py / server.py | Local PDF/OCR and bounded subprocess | Update parser threat model and failure fixtures |
| rag_lab/queue.py | Outbox publication and queue metrics | Preserve publish-before-mark, replay and backpressure behavior |
| rag_lab/worker.py | Redis consumer group and pipeline stages | No long DB locks across inference; finalization must be fenced |
| rag_lab/ui/app.py | Tenant-session API console | No global content cache, DB keys or unsafe HTML |
| migrations/ / alembic.ini | DDL and RLS policies | Do not rewrite an applied migration |
| docker/init-db.sh | Roles/extension for a new volume | Existing volumes need explicit role/schema migration |
| Dockerfile / docker-compose.yml | Isolated services and test profile | Recheck image/dependency security and health/volume paths |
| scripts/setup.py | Generate local secrets once | Never overwrite existing secrets or print credentials |
| scripts/docker.ps1 | Setup, startup, tests, shutdown | Fail on nonzero exits; preserve volumes |
| scripts/upload.py | Streaming CLI client | Reuse upload key on network retry |
| monitoring/ | Prometheus rules and provisioned Grafana | Verify queries and notification routing in target deployment |
| examples/ | Original public PDF, labeled mixed fixture, hashes, question set | Keep source mapping and modified-document label accurate |
| tests/ | Core, API, storage, PDF, UI and database checks | Database tests only on *_test; no paid inference by default |
| docs/security.md | Controls and production gaps | Update alongside code, not as an afterthought |
| docs/live-experiment.md | Measurement, assumptions and quality rubric | Use for every published result |
| docs/docker.md / logging.md | Operations, monitoring, backups and diagnosis | Distinguish configured from actually verified |
| docs/verification.md | Build-session checks and blockers | Record exact checks and skipped dependencies |
| docs/demo-script.md | Repeatable portfolio walkthrough | Never present demo-mode estimates as live LLM savings |

There is no native PostgreSQL workflow, no Kubernetes configuration and no automatic cloud provider connection in this version.
