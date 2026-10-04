# Decisions

## 10. Dedicated localhost ingress gateway
**Decision:** Publish localhost ports through Nginx on an ordinary bridge plus a separate internal ingress network; keep application networks internal.
**Why:** Docker can silently omit host bindings for containers attached only to internal bridges. A dedicated gateway restores host access without giving application services a direct external network.
**Tradeoff:** One more trusted service processes plaintext HTTP. Fixed upstreams, no request access logging, no proxy buffering, non-root execution and no application secrets limit its scope. Production still needs TLS and audited egress controls.

## 1. A paired experiment, not a sales claim
**Decision:** Compare full reviewed text with retrieved text and preserve negative savings.
**Why:** Smaller generation input does not establish lower total cost or equal answer quality.
**Tradeoff:** Requires explicit price assumptions, quality review and reproducible snapshots.

## 2. PostgreSQL + pgvector
**Decision:** Store status/configuration plus encrypted content and exact cosine-search vectors in PostgreSQL.
**Why:** One transactional store makes tenant policies, outbox and reproducibility inspectable.
**Tradeoff:** Vectors cannot remain encrypted while using ordinary pgvector similarity search; protect disks/backups and access.

## 3. Redis Streams delivery with PostgreSQL outbox
**Decision:** Streams consumer groups deliver IDs; DB leases fence work and retain durable state.
**Why:** The user requested horizontal consumers and Redis. Lost notifications can be reconstructed.
**Tradeoff:** Two operational services; at-least-once execution still needs idempotent writes and recovery.

## 4. Local parsing and explicit human review
**Decision:** Isolate PDF/OCR and require review before indexing.
**Why:** Confidential material must not silently go to a hosted parser; diagrams and scans can lose meaning.
**Tradeoff:** Optional local vision supplies model-generated diagram descriptions and table cells; they need verification. No handwriting promise or malware/CDR certification. See docs/ingestion.md for limits and provisioning.

## 5. Targeted LangChain usage
**Decision:** Use splitters, embeddings and prompt composition; retain explicit repository and accounting.
**Why:** Reuse useful interfaces while preserving visible authorization and cost boundaries.
**Tradeoff:** More domain code than a one-call vectorstore chain. LangGraph deferred until graph branching warrants a second state mechanism.

## 6. Two chunking treatments initially
**Decision:** Recursive token-bounded children and bounded page-local parent expansion.
**Why:** A clear baseline and a context-completeness tradeoff are measurable with a small question set.
**Tradeoff:** Semantic chunking, reranking, full layout reconstruction and HNSW remain experiments, not claimed features.

## 7. Private demo and local models
**Decision:** Synthetic lexical demo by default; optional private Ollama. No hosted provider adapter yet.
**Why:** Confidential-document external processing was not authorized.
**Tradeoff:** Default results are not real LLM measurements; USD is an editable token-price scenario, not a bill.

## 8. Observable operations
**Decision:** Prometheus histograms/counters, Grafana provisioning and structured metadata-only logs.
**Why:** Queue age and stage latency expose actual bottlenecks and failed attempts.
**Tradeoff:** External alert delivery, production traces, SLOs and immutable audit storage remain deployment work.

## 9. Shared encrypted volume first
**Decision:** Stream encrypted PDF frames to a shared named volume through a small blob adapter.
**Why:** Reproducible local Docker setup without adding a second storage server.
**Tradeoff:** Multi-host consumers require a shared object-store adapter; current scaling is multiple containers on one host.
