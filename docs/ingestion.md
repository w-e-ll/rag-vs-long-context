# PDF extraction v5

V5 groups connected colored figure regions before OCR and attempts polar unwrapping for compact circular figures. This is a bounded geometric heuristic, not general diagram understanding. The NIST wheel's six outer labels and three inner labels are recovered in local OCR checks; known `Al Model`/`MAP I` label confusions receive narrow, review-marked normalization. Core Map/Measure/Govern/Manage labels and their text remain in separate regions. Colorless figures, unusual ring widths, overlapping regions and arrows remain limitations. Original figure OCR is retained as a raw provenance block; region output is used in canonical text. Native text and recovered blocks are interleaved by page position rather than appending every figure after the footer.

Diagram model responses use a schema without tables. Table output is permitted only when the baseline page contains a numbered Table caption; unsupported table output fails validation instead of displaying invented rows. This routing is conservative and may miss captionless tables. Schema validation still cannot establish factual accuracy of descriptions, which remain excluded from canonical text until manually verified.

Local Windows Tesseract checks cover column separation, scanned table cells, wheel labels, separate Core regions and figure-before-caption ordering. Live Docker/Linux and GPU model behavior are not verified by those checks. OCR may still read `AI` as `Al`, `1` as `I`, or merge `on a` into `ona`. The parser applies only two explicit, auditable label fixes (`Al Model` → `AI Model` and `MAP I:`/`MAP I.` → `MAP 1:`/`MAP 1.`), and adds a review warning when either fires; arbitrary words, identifiers and numbers remain unchanged.

V4 adds conservative raster-table extraction: detect long horizontal rules, infer header gutters, assign OCR words to cells, and reject gutters crossing words. The NIST MAP scan now has separate header, MAP 1 and MAP 2 rows and two columns without a vision call. This targets aligned ruled tables, not arbitrary skewed/borderless/merged layouts. OCR can still confuse `1` with `I`; cell reconstruction is not character-level verification.

Colored list-marker OCR lookalikes are normalized only when their pixel color supports a marker; ordinary black letters are unchanged. Colored scan figures are cropped for vision to avoid spending image context on surrounding prose.

Model responses remain unverified suggestions in raw blocks and are no longer appended automatically to canonical text. A reviewer must copy verified information into reviewed text. `completed` remains the transport/schema status for compatibility; the UI labels it “response received — unverified.” A stronger extraction prompt is not a guarantee against incorrect labels/grouping. Existing saved documents retain their old content; upload again for v4.

The v3 update masks native glyphs inside image crops before OCR, so native captions and headers do not return as noisy duplicates. A conservative colored-panel detector uses OCR word coordinates to read each panel as a separate column. This fixes the NIST three-panel figure; it is not a general guarantee for borderless, monochrome or irregular layouts. Word confidence does not measure reading-order accuracy.

Vision on mixed pages uses the union of recovered image regions rather than the whole page. Individual timeout/invalid-output failures no longer suppress later figures; document time and call limits still apply. Warnings distinguish request timeouts, unavailable services, HTTP failures, incomplete output and invalid evidence. Incomplete calls display unavailable usage rather than implying zero cost.

For a short native OCR regression check, run `./scripts/docker.ps1 CheckOCR`. This builds the test image and checks column separation and caption masking without a model call. For this hardware, use `./scripts/docker.ps1 Up` as the normal stable deployment: it uses OCR, geometry tables and deterministic figure-region OCR without starting the slow vision model. Existing extraction results are immutable.

Local validation: the nine-page fixture extracted with a Windows Tesseract 5 runtime; explicit page-3 column/caption assertions passed. The Docker/Linux OCR check and live GPU vision quality/timing require verification in the running deployment.

The old pipeline merged some native words, skipped images on pages with readable text, and missed tables without vertical borders. The screenshots of the NIST fixture reproduce these failures. Review is a quality gate, not a replacement for extraction.

## Processing

1. Validate PDF size, page count, dimensions and active content inside the isolated parser.
2. Recover native text with a font-relative word-gap tolerance (`x_tolerance_ratio=0.1`, absolute fallback 1 point). This fixes the NIST merged-word regression without guessing words from a dictionary. Line-ending hyphenation is retained rather than silently rewriting compound words.
3. Recover ruled tables as cells. For tables with horizontal rules only, infer columns from repeated segment endpoints. Preserve empty cells and page provenance; do not invent the missing category on a continued page. Extract prose outside those regions to avoid duplicate/interleaved table text.
4. Render scans at 216 DPI and run local Tesseract. On mixed pages, also OCR image regions even when native prose is present. Suppress OCR lines already in native evidence. Keep mean OCR confidence; it is a recognition diagnostic, not a probability of factual correctness.
5. When enabled, send pages containing images, scans, tables or substantial vector drawings to the fixed private vision service. Qwen2.5-VL returns validated JSON descriptions and table rows. Record model tag, input/output token counts, wall time and completion/failure status. Never silently replace reliable native text with a model rewrite.
6. Present raw extracted blocks plus canonical editable page text. Both experiment arms consume only the approved canonical text. Original blocks are retained for provenance and may differ after manual corrections.

Vision may duplicate OCR labels or a geometry table. Review and reconcile conflicting versions in the canonical text before approving. Unreadable values, uncertain relationships, disabled vision and failures are visible warnings. Plain OCR cannot infer the wheel's relationships; the UI marks unresolved visual structure and preserves region-level evidence rather than inventing arrows or relationships. A successful model response still requires checking against the source. Borderless tables without repeated rules rely on the vision path. Rotated/handwritten/low-resolution pages and complex merged cells are not guaranteed.

## Local vision on an 8 GB NVIDIA GPU

Qwen2.5-VL 3B is an optional experiment on this machine, not a production dependency. The measured GTX 1070 result is about 0.4 generated tokens/second and an invalid structured response after 116 seconds on a tiny synthetic diagram. OCR-first mode is therefore the supported path for this project. The generation provider can remain in demo mode while deterministic extraction is real.

From the project directory:

```powershell
# Once: download public model weights into a dedicated volume.
./scripts/docker.ps1 DownloadVision
# Optional experiment only; expect minutes per page and unverified output.
./scripts/docker.ps1 Up -Workers 2 -Vision -Gpu
./scripts/docker.ps1 Verify
./scripts/docker.ps1 Test
```

Starting without `-Vision` deliberately returns the parser to OCR/geometry-only mode and is the recommended deployment on this laptop. Vision failures never replace baseline evidence, but they can add up to 240 seconds per selected page when enabled.

The downloader has internet access and only the model volume. Runtime vision has no published port and uses an internal network shared only with the parser. No document, application key, database or blob volume is mounted in the downloader. Run provisioning separately from ingestion; do not pull/update weights while processing documents. Record the model digest from `ollama list` before publishing benchmark results.

Re-upload the fixture after rebuilding. Existing extraction/index versions are immutable and are not automatically rewritten. A new upload uses `pdf-v5`; old documents remain visible with an upgrade notice.

## Acceptance checks on the nine-page fixture

| Page | Required evidence |
|---|---|
| 2 | Words separated in “also pose risks that can negatively impact” and the AI-system definition |
| 3 | OCR contains Harm to People / Organization / Ecosystem; vision describes the groups |
| 4 | Vision describes the center, rings and lifecycle relationships; curved labels checked visually |
| 5 | Scan OCR recovers prose; vision describes Valid & Reliable as the base and the vertical accountability box |
| 7–8 | Two-column Categories/Subcategories tables; GOVERN 2 and its subcategories remain in their respective cells |
| 9 | Scan OCR contains MAP; vision recovers table cells and preserves numbers |

Inspect `vision_status=completed` on visual pages when testing the vision setup. `failed`, `disabled` or `budget_exceeded` means visual extraction is incomplete, even if prose is available. Correct or reject uncertain output before indexing.

Extraction uses two passes: complete native text, geometry tables and OCR first, then enrich visual pages. Limits: 12 OCR regions/page, 10 vision calls/document, up to 240 seconds/vision call and 1200 seconds for the vision pass. The vision deadline also stays inside 1380 seconds from extraction start, leaving headroom before the 1500-second parser hard limit. Failed pages do not suppress subsequent calls while time/call budgets remain. Scans are prioritized; native tables already recovered as cells skip model inference unless the page also contains images or substantial vector figures. A slow model returns baseline evidence with failed/budget-exceeded warnings rather than discarding it; the hard limit can still reject an excessively slow baseline extraction. Work remains single-slot with worker lease renewal. Extra workers cannot accelerate one GPU and may receive bounded busy retries. No new paid API or tracing service is used.

Measured user diagnostic: GTX 1070, CUDA v12 backend, 37/37 layers offloaded, approximately 5.2 GiB total runner memory. Three successful generation requests took 147–173 seconds; later calls hit the old 180-second timeout and the old whole-document limit stopped processing at 900 seconds. These are observed HTTP timings, not verified extraction-quality scores. Allow roughly 15–20 minutes for the first full fixture run; this estimate is not a latency guarantee. The larger budget and selective routing have not yet been measured on the user's GPU.

Shared extraction is excluded from the existing RAG-vs-long-context generation USD estimate. Its time and vision usage are reported separately; local energy/hardware cost is not zero just because there is no API invoice. Failed attempts and process timeouts may have incomplete usage reporting.

Sources: [pdfplumber extraction/table settings](https://github.com/jsvine/pdfplumber), [Qwen2.5-VL 3B](https://ollama.com/library/qwen2.5vl:3b), [Ollama structured image generation](https://docs.ollama.com/api/generate).
