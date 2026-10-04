# Verification record

## Publication preparation — 4 October 2026

- Final publication copy: **107 tests passed, 8 skipped** in the existing isolated Python 3.13 test environment. Project `uv run --frozen --no-sync` could not query its interpreter due to host access restrictions. A fresh dependency installation was not verified.
- Skipped: five native Tesseract checks and three PostgreSQL/queue integration checks requiring an isolated test database. Docker services and application data were not changed during this preparation.
- Ruff lint and formatting pass across 78 Python files. Seven files received formatting-only changes; Python AST comparison confirmed unchanged logic.
- README includes the episode 03 video, clickable local thumbnail and LinkedIn contact. Local README file links resolve.
- Publication scan found no matches for local credential values or checked private-key/GitHub/AWS token patterns. Local `.env`, demo credentials, virtual environment and editor caches are excluded by Git; `.env.example` remains included. This is a targeted check, not a comprehensive security audit.

## Vision timing probe - 2026-10-02

User runtime logs confirm CUDA on GTX 1070, 37/37 layers offloaded, roughly 5.2 GiB
runtime allocation and 9.44/19.41-second runner startup. Calls completed in 128–226 seconds
or were canceled at 240 seconds. VRAM recovery warnings follow unload; they do not by
themselves establish OOM or CPU fallback. The bottleneck is not yet identified.

`./scripts/docker.ps1 CheckVision -Gpu` sends one synthetic two-box image through the same
adapter and current request settings. Run when document processing is idle to avoid GPU
contention. It loads local diagnostic code into the existing parser process invocation via
stdin, without an image rebuild, persistent edits, customer input or secret output.
It prints wall time and numeric Ollama load/prompt/generation timings, when returned;
timeout produces a safe code without pretending unavailable timings are zero. A tiny
fixture is not a PDF quality benchmark or proof of production latency. No timeout or
model/context/image-size setting was changed based only on the logs.

Validation: 15 focused adapter/probe tests pass, Ruff passes and PowerShell script parses.
Actual hardware measurement is pending. Timing definitions follow the
[Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md).

The synthetic probe timed out at 240.297 seconds. Vision requests are now bounded to a
1280-pixel image, 4096-token context and 512 generated tokens, with a 10-minute model
keep-alive to avoid repeated reloads. These are an optimization hypothesis, not a claimed
result; rerun `CheckVision -Gpu` and compare the numeric timings before changing them again.
The transport now requests generic JSON instead of Ollama full-schema constrained decoding;
the complete `DiagramResult`/`VisualResult` Pydantic validation remains mandatory before
any model output becomes evidence. This targets the observed GPU-specific stall without
weakening the acceptance boundary.

## Scanned figure/caption separation - 2026-10-02

- The user's next result exposed full-page panel detection interleaving figure labels and
  the caption on the scanned trustworthiness page. Scans with a bounded colored figure now
  OCR the prose above/below independently and recover the figure's individual regions.
  Existing recovered tables keep their separate path. Raw uncertain glyphs are not guessed.
- Region extraction supports up to 12 boxes, retains standalone ampersands, removes
  edge-connected artifacts from inverted rounded-box masks, and avoids duplicate OCR variants.
- Removed the generic vision prompt's circular-band assumption. This does not establish
  semantic accuracy or solve the observed 240-second local inference timeouts.
- Local suite: **80 passed, 8 skipped**; Ruff passes. Real Windows Tesseract checks passed
  the existing circle/core diagrams and the new seven-box scan with caption order verified.
  Linux native OCR and latest full Docker suite remain to be run by the operator.
- Remaining known issues include ambiguous I/l/1 glyphs, some hyphenation and bullet loss,
  inferred visual relationships and vision performance. No production quality claim.

## Figure OCR precision follow-up - 2026-10-02

- User's full Docker suite before this follow-up: **83 passed in 55.11s**.
- Subsequent screenshots exposed false-positive circular labels despite passing recall checks.
  Ring extraction now isolates label ink regions and selects one orientation per region,
  preferring readable original pixels before transformed fallbacks. It no longer unions
  overlapping windows and both orientations. No NIST label dictionary is used.
- Regression checks now require exactly four inner and six outer labels on this fixture,
  reject the observed fragment/reversed duplicate and retain the existing label assertions.
- Visible line-wrap hyphens retain their spelling unless the joined word is corroborated
  elsewhere in extracted evidence. Raw table cells remain unchanged; serialized table text
  receives the same conservative cleanup. Numeric IDs and OCR character substitutions are
  not guessed.
- Latest local suite: **80 passed, 7 skipped**; Ruff lint and format pass. Additional real
  Windows Tesseract C-API runs passed diagram and scanned-table regressions. These do not
  substitute for the Linux image run: execute `./scripts/docker.ps1 CheckOCR` after rebuilding.
- Known unresolved examples: `AI` versus `Al`, `MAP 1` versus `MAP I`, a missing bullet,
  and some uncorroborated hyphenated words. Model/mean OCR confidence is not proof of
  correctness. The diagram regression does not yet assert exact recovery of `AI Model`.

## Private-server hardening - 2026-10-02

- User-host `CheckOCR`: **7 passed in 13.71s**. This closes the missing-label
  regression on the public fixture in Linux; it does not establish general OCR accuracy.
- Latest local suite: **76 passed, 7 skipped**. Ruff check and format pass (68 files).
  Skips require native OCR or isolated PostgreSQL/Redis services unavailable here.
- Tests cover parser admission before buffering, transfer limits, cancellation retaining
  capacity, English OCR readiness, credential expiry/disable and production startup guards.
- Busy parser responses now defer jobs without exhausting extraction attempts. Unit tests
  cover deferral at attempts 1 and 3 and distinguish real OCR failures. The new PostgreSQL
  test checks repeated deferral, redispatch delay and stale-lease rejection; it is skipped
  locally and must pass in the full Docker suite.
- Combined base/vision/GPU Compose configuration validates. Docker client configuration
  access emitted a sandbox warning; no running service or GPU behavior was verified here.
- Run `./scripts/docker.ps1 Test` on the Docker host to validate this latest code.
  Prior CheckOCR results do not validate subsequent queue/auth/parser admission changes.
- Production release remains blocked by the gates in [production-readiness.md](production-readiness.md).

## PDF v2 - 2026-10-01

GTX 1070 follow-up: user diagnostic confirms GPU assignment, CUDA v12 and 37/37 layers offloaded. Successful requests took 147–173 seconds each. The proposed 90-second call limit was corrected before deployment to 240 seconds, with a bounded 1200-second optional pass and 1500-second hard parser limit. Native geometry tables now skip redundant inference. **52 tests passed, 3 skipped**; GPU end-to-end verification of these changes remains pending.

Timeout follow-up: the user's parse failed after 900 seconds, matching the subprocess deadline. Added a baseline-first extraction pass, bounded optional vision enrichment and allowlisted parser errors. **51 tests passed, 3 skipped**, including simulated vision timeouts, preservation of all nine fixture pages and safe error propagation. Actual GPU use remains unconfirmed: host nvidia-smi reports GTX 1070, but the supplied model log tail contains only health checks. `scripts/docker.ps1 DiagnoseVision` reads device requests and filters routine health logs.

- Isolated Python environment: **44 passed, 3 skipped**; Ruff lint and formatting pass.
- Actual NIST native-text and horizontal-rule table regressions pass. Mixed-page OCR routing, scan/vision evidence merging, failure states, response bounds and table review UI are tested with controlled OCR/model doubles.
- Skips: live Tesseract fixture extraction, PostgreSQL and Redis integration. Tesseract is installed in the Docker image, not in this agent's local test environment. Earlier user-run v1 integration results do not validate v2 OCR.
- Base and vision/GPU Compose configurations validate. Runtime internal-network isolation, no published vision port, downloader volume isolation, PowerShell syntax and dashboard JSON checks pass.
- Docker named-pipe access remains denied. Model weights were not downloaded by the agent. Real OCR quality, GPU execution, vision JSON/diagram accuracy, scanned table cells and full upload-to-review behavior must be validated on the user's Docker host using docs/ingestion.md. Do not report these as completed checks.
- User's prior gateway output confirms Nginx configuration validation, healthy gateway and all four reachable host endpoints.

## Original build

Gateway follow-up: user logs confirm Nginx failed to create `/var/cache/nginx/fastcgi_temp` on the read-only filesystem. Three default module temporary directories were still outside the writable tmpfs; all five are now explicitly under `/tmp`. Compose validation and static temporary-path checks pass. Successful recovery and Nginx runtime validation still require `docker compose run --rm --no-deps gateway -t` and Verify on the user's Docker host.

Executed with the isolated Python 3.13 environment:

- `pytest -q`: **35 passed, 3 skipped**.
- `ruff check .`: passed with a writable cache directory.
- `ruff format --check .`: passed; all Python files are formatted.
- API, queue, worker and parser import smoke check: passed.
- NIST source extraction: 48 pages; mixed fixture: 9 pages with two raster-only pages.
- Fixture contact sheet was visually inspected.
- User-provided Docker test output: **38 passed** (including the previously skipped integration/OCR checks). This was executed in the user's PowerShell session, not the agent sandbox.
- The user subsequently reported healthy API/database/Redis containers, but absent host port bindings. The gateway networking fix passes Compose configuration validation and PowerShell parser validation. Live gateway startup, Nginx configuration execution, browser WebSockets, host HTTP reachability and Grafana provisioning remain unverified because the agent cannot access the Docker named pipe.
- PostgreSQL/Redis integration tests require `TEST_DATABASE_URL` ending in `_test` and `TEST_REDIS_URL` ending in `/15`.
- No hosted AI provider, LangSmith tracing or paid API call was used. Ollama execution remains unverified.

Run the remaining checks from PowerShell with Docker Desktop access:

```powershell
uv sync --frozen
./scripts/docker.ps1 Up -Workers 2
./scripts/docker.ps1 Verify
./scripts/docker.ps1 Test
```
