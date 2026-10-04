# Experiment methodology

The hypothesis is **RAG is not automatically cheaper**, not that any particular strategy wins.

## Controls

Both arms receive the same question and approved extracted source, use the same generation model/prompt/output cap, and snapshot chunk settings and illustrative prices. The long-context input contains every reviewed page. RAG receives the selected child blocks or deduplicated parent blocks, subject to a token budget. Run UUID parity alternates order approximately across repeated trials; use balanced repeated runs to control cold-start and warm-cache effects.

Use the small mixed fixture for a practical demo. Use the complete NIST document only if it fits the configured long-context experiment bound. Refusal is explicit; no silent truncation is requested by the application. Ollama num_ctx defaults to 8192, configurable through LLM_CONTEXT_TOKENS. Prompt checks reserve output space and proxy-token headroom. cl100k_base is a proxy, not its exact tokenizer, so review model usage and context capacity before larger real-model experiments.

## Measurements versus assumptions

| Field | Meaning |
|---|---|
| generation input/output tokens | Model-reported for Ollama; synthetic for lexical demo |
| generation latency | Local wall-clock time of the invocation |
| retrieval_ms | Query embedding + SQL lookup + context packing |
| rag_end_to_end_ms | Retrieval/embedding + RAG generation; excludes queue wait and shared parsing |
| indexing_tokens | Cumulative known newly-computed embedding-token estimate for this document across indexing attempts |
| indexing_ms | Most recent successful indexing wall-clock duration |
| USD | Scenario estimate from snapshotted user-entered rates |
| first_question_savings | Full-context generation less indexing, query embedding and RAG generation |
| projected_savings | Repeated observed query cost at chosen N, less cumulative indexing |
| break_even_questions | First integer N with strictly positive projected savings; null if no advantage |
| fact_coverage | Case-insensitive normalized substring matches of user-specified facts; not correctness |

A cached embedding has no new embedding-token estimate. Embedding work is recorded as soon as its completed vector is stored; after a crash before that transaction commits, local compute may be repeated and its previous usage is unknown. Cumulative document indexing is deliberately conservative when trying multiple chunking settings. To compare isolated cold-start settings, upload separate document versions or account for warm reuse explicitly.

There is no cloud billing adapter. Infrastructure, OCR compute, energy, review labour and incomplete generation attempts are excluded from the token-price scenario. Report these omissions alongside any cost-saving claim. A failed/unknown experiment has no invented zero-cost successful result.

## Evaluation set

`examples/questions.json` includes prose, table, continued-table, scanned-page, diagram and unanswerable tasks with expected pages/facts. Review the questions against the source. For each answer, manually assess correctness, completeness, citation support and abstention. Measure retrieval evidence coverage separately from answer quality. Literal fact coverage is an inexpensive diagnostic and can reward an incorrect statement containing the expected words.

NIST may be represented in model training data. To check true grounding, add synthetic facts/numbers to a separately labeled private test document; never describe a modified fixture as an official NIST publication. Do not send confidential evaluation content to a hosted judge by default.

## Chunking experiments

1. Recursive token-bounded baseline: 450 tokens, 60 overlap; vary 250/450/750 while keeping retrieval context budget constant.
2. Parent-child: 450-token children, page-local parents capped at 1400 tokens. Retrieve small children; expand parents, deduplicate and enforce budget. Larger evidence can improve completeness and increase cost.
3. Semantic chunking is a planned additional experiment, not implemented in v0.1. It adds sentence embeddings/threshold choices and must include preprocessing cost. There is no assumption that it wins: see [Qu et al.](https://arxiv.org/abs/2410.13070).

Token limits and semantic boundaries are complementary; parent-child describes indexing/retrieval granularity and can coexist with either. Parser quality must be held constant when comparing chunking methods.

## Private model setup

The default demo performs no model downloads. To run Ollama, first import approved model files into the `ollama_models` volume through an operator-controlled provisioning process, then set `PROVIDER_MODE=ollama` and start the `local-models` profile. The runtime network has no internet egress; `ollama pull` inside the isolated service will not work until an explicit model-provisioning network is provided. Do not weaken the runtime network to allow confidential-document egress.

The configured defaults are `nomic-embed-text` (768 dimensions) and `llama3.2:3b`. Pin actual model digests in any published benchmark report; model tags alone are insufficient for strict reproducibility. This build has not downloaded or executed them. See [laptop text model setup and presentation evaluation](text-model-demo.md) for the DownloadText and UpText commands.
