# 1) REQUIREMENTS.md review (critical)

## What was wrong with the original REQUIREMENTS.md

- **Not aligned with the repository**: it described a “universal ingestion engine” (DOCX/PPTX/XLSX/HTML + Docling + PaddleOCR, unified `ingestion.jsonl` schema) that is **not implemented** in this repo.
- **Not testable / not verifiable**: many statements were aspirational (“100% contextual integrity”) without acceptance criteria.
- **Schema errors/ambiguities**: e.g. `classification` union had a syntax error (`"sidebar"  "ad"` missing `|`).
- **Mixed “requirements” with dev hints** (tool choices for “Cline”) rather than normative product requirements.

### What I changed

I rewrote REQUIREMENTS.md to be:

- **Scope-correct** (current implementation: local PDF+EPUB pipeline, optional Surya, Tesseract OCR)
- **Verifiable** (explicit artifacts, schemas, and CLI acceptance checks)
- **Standards-compliant** (clear in/out of scope, glossary, functional + non-functional requirements, verification section)
- Added a **Requirement → verification matrix**.
- Clarified that **non-PDF formats** that PyMuPDF can open (docx/pptx/xlsx/html) are **experimental/best-effort**, unless promoted to first-class support with dedicated acceptance criteria.

Updated file: `REQUIREMENTS.md`

---

## 2) Verification: does the application meet the requirements?

### Automated tests

- ✅ Unit tests: `PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'` → **OK (10 tests)**

## CLI smoke tests executed (representative)

- ✅ `inspect`:
  - PDF: `PCWorld_July_2025_USA.pdf`, `IRJET_Modeling_of_Solar_PV_system_under.pdf`, `Firearms.pdf`
  - EPUB: `Seffer, David - ... .epub`
  - Also observed: `.docx/.pptx/.xlsx/.html` are opened by PyMuPDF and return metadata.
- ✅ `convert` PDF (magazine) → produced `pages_raw.jsonl`, `doc_meta.json`, `blocks_structured.jsonl`, `chunks_text.jsonl`, `structure_report.txt`.
- ✅ `convert` EPUB → same outputs.
- ✅ OCR flow:
  - Synthetic scanned PDF → `pages_with_ocr.jsonl` created, `from_ocr=true`, and `evaluate` produced `quality_report.json` with `ocr_coverage=1.0`.
- ✅ Multimodal export linking:
  - After `render-pages` on IRJET, `chunks_multimodal.jsonl` contained `page_images`.
- ✅ Figure extraction:
  - `convert --extract-figures` on IRJET produced `figures.jsonl` + `figures/*.png` and `chunks_multimodal.jsonl` attached figures.
- ✅ Determinism check (IRJET, two runs): hashes were identical for all key artifacts.

### Regression test

- ✅ `mmrag-convert regression --docs-dir examples/sample_docs ...` ran across **10 PDF/EPUB docs** and finished **Regression OK**.

**Conclusion:** against the *updated, scope-correct* REQUIREMENTS.md, the system largely complies.

---

## 3) Issues found (critical, with evidence)

Even though regression passes, there are real “hard-task” quality problems that will hurt multimodal RAG ingestion.

### P0 — Chunk size not enforced: oversized chunks can exceed `--max-tokens`

- Evidence: EPUB smoke run (`--max-tokens 300`) produced chunks with `tokens_estimate` up to **609**.
  - Example: `..._c0201 tok=609`, `..._c0552 tok=364`.
- Why this matters: embedding models / retrievers typically have strict max token limits; oversize chunks break ingestion or require downstream truncation.

### P1 — OCR is being run on non-PDF formats and can inject garbage text

- Evidence: HTML conversion with `--ocr-scanned-pages` generated `pages_with_ocr.jsonl` where a page had `from_ocr=true` but produced obvious garbage:
  - sample: `ae ner! ae es a 5 ¢ ...`
- Root cause: `convert` runs OCR for any non-EPUB document when `--ocr-scanned-pages` is enabled (default), and PyMuPDF can render HTML/Office “pages”.
- Risk: “garbage OCR” becomes canonical text for the page, harming retrieval.

### P1 — Doc domain detection can misclassify (affects heuristics)

- Evidence: `PCWorld_July_2025_USA.pdf` was classified as `doc_domain=academic` in regression.
  - signals: `scores {'academic': 1, 'manual': 0, 'book': 1}`.
- Impact: downstream structure/filters are domain-aware; wrong domain changes chunk filtering and heading detection behavior.

### P2 — Surya layout ordering can be low-quality on graphic-heavy pages

- Evidence: running Surya on PCWorld page 1 produced fragmented/duplicated lines (cover text repeated).
- This reduces contextual integrity and can create “heading spam” style blocks.

### P2 — Documentation/UX mismatches

- `convert` prints “Skipping full-page PNG rendering (REQ-M1)” but **REQ-M1 no longer exists** (and the repo behavior is now specified under REQ-RENDER-2).
- `inspect` prints `PDF:` even for EPUB/HTML/Office docs (minor, but confusing).

### P3 — Path portability inconsistency

- `page_images` are often relative (e.g. `workdir_smoke_render/pages/.../p001.png`), while extracted figure `image_path` can be absolute (because `workdir` is resolved).
- This makes `chunks_multimodal.jsonl` less portable across machines.

---

## 4) Plan to fix issues (verifiable steps; no implementation yet)

### Fix plan A (P0): Enforce chunk size without mid-sentence splits

1. **Add failing tests**:
   - New unit test feeding list-like text (newlines/bullets/URLs) and asserting `tokens_estimate <= max_tokens + slack` for all chunks.
2. **Improve segmentation strategy**:
   - Enhance sentence splitting to treat:
     - newline-separated list items
     - bullets (`-`, `•`)
     - URL lists and “Sources/Links” sections
     as boundaries.
   - If a “sentence” is still > max_tokens+slack, add a **secondary split** (paragraph/line/word fallback) with explicit marker (still avoid splitting inside words).
3. **Add quality metric + regression gate**:
   - Add `chunks_over_max_tokens` + `chunks_over_max_ratio` in `quality_report.json`.
   - Make `regression` fail if ratio > threshold.

Acceptance criteria:

- For a fixed corpus run, `tokens_max` must be ≤ `max_tokens+slack` for ≥99.9% of chunks and 100% for common cases.

### Fix plan B (P1): OCR gating + OCR quality filtering

1. **Gate OCR execution**:
   - Only run OCR when `scanned_like_pages > 0`.
   - Restrict OCR to **PDF only** by default (or explicitly make “PyMuPDF-renderable docs” supported, but then document it).
2. **OCR sanity check**:
   - After OCR, reject text that fails quality heuristics (e.g. too few alphanumerics, extremely low dictionary hit rate, too many symbols).
   - If rejected, keep page `is_scanned_like=true` (or mark `from_ocr=false`) and do not replace the page text.
3. **Integration tests**:
   - Synthetic scanned PDF (good OCR) must pass.
   - Synthetic “noise” page must be rejected and not overwrite text.

Acceptance criteria:

- No `from_ocr=true` pages with low text quality scores.
- `ocr-fallback` runtime does not trigger on documents with 0 scanned-like pages.

### Fix plan C (P1): Improve doc domain detection

1. Add targeted unit tests:
   - Minimal text snippets from magazines/manuals vs academic papers.
2. Improve heuristics:
   - Add magazine/manual keywords (“issue”, “tested”, “review”, “laptop”, “PCWorld”, etc.).
   - Add tie-break rules (when scores tie, prefer manual for magazine-like patterns; otherwise book).

Acceptance criteria:

- PCWorld-like docs classify as `manual` (or introduce a `magazine` domain).

### Fix plan D (P2): Make Surya optional path robust

1. Add a per-page “layout quality score”:
   - detect severe fragmentation (very short lines, duplicates), extremely low char count, repeated blocks.
2. If Surya output is low quality → fallback to heuristic ordering.
3. Add a reproducible integration test using a known multi-column sample.

Acceptance criteria:

- Covers/graphics do not produce duplicated/fragmented output compared to fallback.

### Fix plan E (P2/P3): UX and portability cleanups

1. Replace “REQ-M1” wording in CLI message to match current requirements.
2. Normalize `page_images` and `figures[*].image_path` to **relative paths** under the workdir.
3. Document experimental formats clearly in README.

Acceptance criteria:

- `chunks_multimodal.jsonl` is portable when moving the workdir.

---

## 5) Next step (your choice)

If you want, I can next switch from analysis/planning into implementation and deliver the fixes in small PR-like steps with:

- new tests first (to lock in regressions),
- then code changes,
- then `regression` thresholds updated.
