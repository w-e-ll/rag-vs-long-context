"""Bounded labels only. IDs and document content are not metrics dimensions."""

from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("rag_http_requests", "HTTP outcomes", ["route", "status"])
HTTP_TIME = Histogram("rag_http_seconds", "HTTP request time", ["route"])
STAGE_TIME = Histogram(
    "rag_stage_seconds",
    "Worker stage time",
    ["stage"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 900),
)
JOBS = Counter("rag_jobs", "Worker attempts", ["kind", "outcome"])
REUSED = Counter("rag_embedding_reused", "Chunk embeddings reused within a tenant")
QUEUE_DEPTH = Gauge("rag_queue_depth", "Pending jobs", ["kind"])
QUEUE_AGE = Gauge("rag_queue_oldest_seconds", "Age of oldest queued job")
READY = Gauge("rag_database_ready", "DB reachable by metrics collector")
PDF_PAGES = Counter("rag_pdf_pages", "Extracted pages by method", ["method"])
PDF_VISION = Counter("rag_pdf_vision_pages", "Visual extraction outcomes", ["outcome"])
PDF_VISION_TIME = Histogram(
    "rag_pdf_vision_seconds",
    "Local vision time per page",
    buckets=(1, 5, 15, 30, 60, 120, 180, 300),
)
PDF_VISION_TOKENS = Counter(
    "rag_pdf_vision_tokens", "Local vision model-reported tokens", ["direction"]
)
