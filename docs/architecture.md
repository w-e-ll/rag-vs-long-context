# Architecture

## Business flow and ownership

Authenticated editor -> bounded streamed upload -> encrypted immutable blob -> transaction inserts document and parse job -> 202 -> outbox dispatcher publishes IDs to Redis -> consumer obtains DB lease -> isolated extraction -> reviewed text -> indexing -> paired experiment -> encrypted result -> tenant-scoped API response.

PostgreSQL is the source of truth for statuses, identities, configuration and results. Redis messages are disposable delivery notifications; they contain only tenant/job IDs, which the worker revalidates against its configured tenant registry and database. No PDF, question, answer or embedding travels through Redis.

## Tables

| Table | Purpose | Writer / lifecycle |
|---|---|---|
| documents | Source digest, immutable upload key, reviewed evidence ciphertext, active index config and cumulative known indexing-token estimate | API creates; workers transition status; editor deletes |
| chunks | Encrypted child/parent content, page provenance, pgvector embedding | Index worker atomically replaces an index; document deletion cascades |
| embedding_cache | Tenant-scoped embedding reuse keyed by text + provider fingerprint | Worker writes completed embeddings; deletion of any document conservatively purges tenant cache |
| jobs | Transactional outbox, request digest, attempts, lease, encrypted request/result | API creates; dispatcher marks delivery; consumers heartbeat/finalize; deletion cascades |

Primary/foreign keys include tenant IDs. Application SQL explicitly scopes by tenant; each transaction sets transaction-local RLS context. Every tenant table has ENABLE + FORCE RLS. Runtime role is neither owner, superuser nor BYPASSRLS. Migrations use a separate owner role.

## Ingestion and retrieval

Blob upload uses framed AES-GCM with a tenant-derived key and document/frame identity as associated data. The footer authenticates frame count. API memory does not grow with the uploaded document; Streamlit's native upload widget does buffer its bounded upload. Workers may read the complete bounded blob for parsing.

Parser runs as an isolated service and executes each PDF in a subprocess. On Linux, CPU/address-space/file-size limits supplement container CPU/memory/PID limits. It has no DB credentials, encryption key or persistent blob mount. A separate internal network connects parser and workers. Parsing has a deadline, and the process group is killed on timeout. Original URI links are never fetched. A raster page uses local English Tesseract; diagram relationships require human verification. There is no automatic multimodal reasoning model in v0.1.

Pages are the source boundary. Recursive splitting prefers paragraphs/newlines/sentences and counts proxy tokens. Parent-child uses bounded page-local parent sections and smaller embedded children; expansion is deduplicated. This is not full layout-aware table reconstruction. Review must fix extraction/reading order before indexing. Tables that span pages require human attention.

Embeddings use 768 dimensions, exact cosine search scoped to one document and tenant. This avoids approximate-index recall confounding a small controlled experiment. Scale benchmarks may justify HNSW later. Switching model/fingerprint requires reindexing.

## Queue and scaling

PostgreSQL job insertion and business-state change commit together. Dispatcher XADDs then marks dispatch time. Crash between those actions creates duplicates; a database claim permits one active lease. SKIP LOCKED and atomic status transitions coordinate replicas. The dispatcher republishes queued/expired work after 30 seconds, including after stream loss/trim. Redis uses AOF every second and noeviction; PostgreSQL reconstruction is still required for durability.

Workers block on XREADGROUP, reclaim stale messages via XAUTOCLAIM, heartbeat the DB lease and finalize with matching lease token and unexpired lease. ACK happens after execution/failure handling; duplicate notifications are harmless. Three crashed/transient attempts lead to a dead/failed job. Parser busy/temporary network failures receive bounded retries. No exactly-once inference guarantee is made.

Scale with `docker compose up -d --scale worker=3`. One container has one worker and one metrics endpoint. Prometheus discovers worker IPs using DNS. Parser currently accepts one PDF process per replica; add parser capacity only after CPU/memory measurements. Private Ollama capacity may be the bottleneck before worker count.

Reviewed evidence becomes immutable after successful indexing: upload a new version to change it. Chunk settings can change when no comparison is active. Each comparison stores source hashes and settings. Completed answers are never recomputed on duplicate run IDs.

## LangChain / LangGraph

LangChain provides Document, recursive splitters, Embeddings, Ollama integrations and prompt/runnable composition. The pgvector repository is explicit SQLAlchemy so RLS, encrypted payloads and accounting remain visible. Generic vectorstore metadata filters are not the security boundary.

LangGraph is not installed: durable stage state and manual-review pause are currently explicit PostgreSQL states. Adding a second checkpoint system would duplicate state. Add LangGraph only for substantive branching/review loops, with tenant-scoped encrypted checkpoint design; it will not replace the queue.
