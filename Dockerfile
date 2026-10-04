FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.13-slim AS runtime
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app TIKTOKEN_CACHE_DIR=/app/tokenizer-cache
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
RUN mkdir -p /app/tokenizer-cache && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
COPY rag_lab ./rag_lab
COPY migrations ./migrations
COPY alembic.ini ./
COPY .streamlit ./.streamlit
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --create-home app && mkdir -p /app/var/blobs && chown -R 10001:10001 /app && test "$(id -u app)" = 10001
USER 10001:10001
CMD ["python", "-m", "rag_lab.api.main"]

FROM runtime AS parser
USER 0:0
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
RUN test "$(id -u app)" = 10001 && test "$(id -g app)" = 10001
USER 10001:10001
CMD ["uvicorn", "rag_lab.ingestion.server:app", "--host", "0.0.0.0", "--port", "8010", "--no-access-log"]

FROM parser AS tests
USER 0:0
RUN uv sync --frozen --no-install-project
COPY tests ./tests
COPY examples ./examples
USER 10001:10001
CMD ["pytest", "-q", "-p", "no:cacheprovider"]
