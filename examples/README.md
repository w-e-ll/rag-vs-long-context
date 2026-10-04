# Public source and mixed fixture

Original: NIST AI 100-1, Artificial Intelligence Risk Management Framework (AI RMF 1.0), January 2023.
Source: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf

`nist-ai-rmf-original.pdf` is the downloaded 48-page source. `nist-mixed-fixture.pdf` is a **modified test extract**, not an official NIST publication. It contains a new cover and original source PDF pages 6, 10, 15, 17, 25, 27, 28 and 31. Source pages 17 and 31 were rendered at 144 DPI and inserted as raster-only pages with no text layer. They are fixture PDF pages 5 and 9.

| Fixture PDF page | Source PDF page | Intended challenge |
|---|---|---|
| 1 | New cover | Explicit provenance / modified-document label |
| 2 | 6 | Digital prose and a callout |
| 3 | 10 | Diagram/table-like figure and prose |
| 4 | 15 | Circular diagram, rotated labels and relationships |
| 5 | 17 | Raster-only prose plus a diagram |
| 6 | 25 | Four-function diagram and supporting prose |
| 7 | 27 | Digital table begins |
| 8 | 28 | Continued table and category relationships |
| 9 | 31 | Raster-only table |

Use PDF page positions rather than printed page labels when comparing ingestion metadata. The manifest records SHA-256 digests. Questions are a small diagnostic set, not a statistically representative benchmark. Missing cases include handwriting, photographs requiring visual reasoning, severely degraded scans and arbitrary multilingual OCR.

Public content is safe to demonstrate without customer secrets; it does not eliminate the need for tenant isolation tests. Never call this public fixture a real confidential customer document.
