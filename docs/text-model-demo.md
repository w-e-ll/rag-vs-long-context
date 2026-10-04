# Real local answers on the laptop

## Structured answer verification

New Ollama runs request JSON with status and evidence claims (text, source, quote).
Both comparison arms use the same contract and output limit. A claim's quote must
occur in an actually supplied fragment of its stated source, allowing whitespace
differences only. RAG validation never uses unselected text from the same page.
Quotes cannot match across separate retrieved chunks. A match establishes text
provenance, not semantic entailment, completeness, or correctness of the claim.
The UI exposes supporting quotes and the original model JSON. Invalid schema,
unknown sources and missing or too-short quotations remain visible alongside the
model answer, but are marked as unverified; when possible, the application may
show an exact source excerpt separately because the model omitted its quote.
That excerpt is labelled as application-derived and is not presented as a model quote.
Their returned token usage
and latency remain in the experiment. There is no automatic retry or answer repair.
Abstentions must have an empty claims list and are still unverified decisions.
Existing experiments are unchanged. Live quality and JSON-mode latency on GTX 1070
must be checked with fresh runs; the unit tests do not establish model reliability.

Run in the project directory, with Docker Desktop running:

```powershell
./scripts/docker.ps1 DownloadText
./scripts/docker.ps1 UpText -Gpu
docker compose exec ollama ollama list
```

DownloadText downloads public llama3.2:3b and nomic-embed-text weights into the
dedicated model volume. The downloader has no document volumes or application keys.
UpText enables Ollama for API/worker, one worker, and an 8192-token model context.
The model runtime remains on the private network. No vision service is started.
If a previous vision container is still running, stop it before the text test to
release GPU memory: `docker compose -f docker-compose.yml -f docker-compose.vision.yml stop vision`.

Re-upload the small public fixture, review and index it with the real embeddings.
Existing demo results remain historical and must not be presented as real model results.
Run one paired experiment at a time. Check that the result reports `ollama`,
`llama3.2:3b`, and `model_reported` usage. GPU allocation can be inspected during
generation with `docker compose exec ollama ollama ps`.

The prompt budget reserves output space and proxy-token headroom. The tokenizer is
still an estimate, not the model's exact tokenizer. Oversized inputs are rejected.
Generation retains the bounded 180-second request timeout. Hardware speed and
answer quality require live validation; no successful model runs are claimed here.

## Presentation evidence

Start with these questions on the reviewed NIST fixture:

1. What are the four AI RMF Core functions? Expected facts: GOVERN, MAP, MEASURE, MANAGE.
2. Which three groups can be harmed by AI systems in Figure 1? Verify all groups against the source.
3. What does MAP 1.5 require? Expected fact: risk tolerances.
4. What subscription price does this document specify? Expect an explicit insufficient-evidence answer.

For each run inspect correctness, completeness and page citations in both answers.
Fact coverage alone is not a quality grade. Keep failures as evaluation evidence.
Both arms now use explicit `[S009]` source identifiers for uploaded-PDF positions;
the result stores their mapping to PDF pages and displays it alongside each answer.
Standalone printed folios are omitted only from model context, not stored evidence.
The same prompt
requests concise source-grounded answers in both arms. Responses are preserved
unchanged and checked for missing/non-standard citations and page numbers absent
from the supplied evidence. Passing this check does not establish that a page
supports a claim. The exact whole-answer refusal `Insufficient evidence in the
supplied reference.` is marked as an unverified abstention and needs no citation;
extra claims or citations invalidate that exemption. Expected-fact coverage remains
unchanged: clear expected facts for the unanswerable question. Historical results
retain their old checks and text. These changes need
a fresh paired run; improved model quality is not established by unit tests.
Use the existing Download experiment JSON button to preserve genuine responses,
model identity, source hashes, timings and price assumptions. Label selected
presentation examples as selected and verified; do not rewrite model answers or
substitute invented measurements. Live results are pending the host run.

Return to lexical demo mode with `./scripts/docker.ps1 Up -Workers 2` (assuming
the base .env still has PROVIDER_MODE=demo). Stop the unused Ollama service with
`docker compose --profile local-models stop ollama` to release model memory.
