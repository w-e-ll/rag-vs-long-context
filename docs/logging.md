# Logging and monitoring

Application events are metadata-only JSON to stdout. Allowed fields include request/job/run/document IDs, status, stage, attempt, count and duration. Exception diagnostics contain exception type plus filename/function/line frames, without messages or locals. Never log request bodies, filenames, SQL parameters, DSNs, raw provider errors, keys, questions or answers. HTTP access logs are disabled for API and parser. Compose bounds log-file size.

Business events include upload.accepted, document.reviewed/deleted, queue.dispatched, worker.started/completed/failed, failure_save_failed, heartbeat_failed, request.rejected and http.request. HTTP responses carry a server-generated X-Request-ID. Queue-to-worker diagnostics correlate by job ID; this is not a full distributed tracing deployment.

Prometheus metrics:

| Metric | Meaning |
|---|---|
| rag_http_requests_total | Request outcomes by bounded route template/status |
| rag_http_seconds | HTTP latency histogram |
| rag_stage_seconds | Worker parse/index/compare and inference/retrieval stage durations |
| rag_jobs_total | Worker attempt outcomes, including retry failures |
| rag_embedding_reused_total | Completed chunk embeddings reused |
| rag_queue_depth | Queued + running jobs by kind, refreshed by dispatcher |
| rag_queue_oldest_seconds | Age of oldest queued job |
| rag_database_ready | Dispatcher dependency access succeeded on its last pass |
| rag_pdf_pages_total | Extracted pages by text/OCR/hybrid method |
| rag_pdf_vision_pages_total | Visual extraction outcomes, including disabled/failed/budget-exceeded |
| rag_pdf_vision_seconds | Local vision page latency histogram |
| rag_pdf_vision_tokens_total | Model-reported vision input/output tokens; shared preprocessing |

PDF metrics count processing attempts returning parsed evidence, not unique billed documents. A parser process killed before returning may leave compute/usage unreported. The operations dashboard includes vision outcome and p95 panels.

No tenant ID, question, answer or document ID is a metric label. Grafana is operator-only; its view spans tenants. Streamlit's operation table is tenant-scoped. UI failure rate uses the latest 100 jobs, including queued/running jobs, and explicitly states its denominator. Grafana p95 uses histogram bucket estimates over a five-minute rate window; compare sample sizes before drawing conclusions.

```powershell
docker compose logs --tail 100 api dispatcher worker parser
```

Alert rules cover monitored service unavailability, stalled queues, worker failures and dispatcher dependency errors. Alerts appear in Prometheus; external notification delivery is not configured. No SLO, uptime guarantee or production monitoring claim is implied by having dashboards.
