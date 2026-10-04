# Portfolio demo script

1. State the hypothesis: RAG is not automatically cheaper; an optimization must preserve sufficient answer quality.
2. Show the original NIST source and the labeled nine-page fixture. Identify raster-only pages 5 and 9, digital tables 7/8, and diagrams 3/4/6.
3. Sign in with the alpha demo token. Upload and show 202/job status. Explain that the API streams encrypted bytes while workers process asynchronously.
4. Open Grafana: service health, queue age and per-stage timings. Explain Redis delivery versus PostgreSQL durable state.
5. Inspect extraction. Compare a table and a scanned page with the original. Add a verified description for diagram relationships; do not claim OCR understands arrows.
6. Approve text; index recursive chunks. Show page provenance and index completion.
7. Ask a question from examples/questions.json. Compare full-context and RAG answers, usage labels, latency, first-question cost and projected break-even.
8. Show a small-document case with negative savings. Change the query count; explain the projection's assumptions.
9. Change to parent-child with the same reviewed evidence and query; observe whether extra context helps quality and increases input size.
10. Ask the unanswerable question. Treat confident unsupported answers as a failure, even if cheap. Demo lexical output is not a real LLM quality benchmark.
11. Reuse the same run ID through the API and show the saved outcome instead of duplicate generation. Stop a worker in a controlled test and observe lease recovery; do not claim this was tested until actually executed.
12. Switch to beta: alpha documents are absent; direct alpha IDs return not-found. Discuss remaining production identity/ACL/KMS requirements.
13. End with the observed result, sample size, mode, assumptions and limitations. No guaranteed savings percentage without real evidence.
