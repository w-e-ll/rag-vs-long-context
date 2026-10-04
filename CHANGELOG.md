# Changelog

## Unreleased - 2026-10-01

- Follow-up: preserve baseline extraction before optional vision, bound its cumulative time and stop after repeated failures. Preserve allowlisted parser failure codes instead of collapsing them into processing_failed.

- PDF v2: font-relative word spacing, OCR of image regions on mixed pages, scan word confidence, and cell extraction for horizontal-rule tables.
- Optional internal Qwen2.5-VL 3B service, separate weight provisioning and GPU override; bounded structured diagram/scanned-table extraction with explicit failure states.
- Review UI shows extraction provenance, table cells, visual descriptions and preprocessing usage/time. Existing documents remain unchanged; re-upload to use v2.
- Added public-fixture spacing/table regressions, mixed-page/scan routing tests and bounded local vision transport tests.

## 0.1.0 - 2026-09-29

- Fixed localhost publication from internal-only networks using a dedicated Nginx gateway; retained internal application isolation, streaming proxying and WebSocket support. Verify now checks all four host endpoints with bounded readiness retries.

- Initial Sunday AI Builds 03 implementation: tenant-scoped PDF ingestion, local extraction/OCR review, LangChain chunking and pgvector retrieval.
- Redis Streams delivery, PostgreSQL job outbox, consumer leases and fenced commits.
- Paired long-context/RAG experiments, signed scenario costs, break-even, usage labels and fact-coverage diagnostic.
- Streamlit UI, Prometheus/Grafana provisioning and alert rules.
- Public NIST source, labeled mixed PDF fixture, evaluation questions and automated checks.
- Production boundaries and unverified container/model checks documented explicitly.
