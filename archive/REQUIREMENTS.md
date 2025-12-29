# Multimodal Doc Converter — Requirements (v0.1.x)

> **Critical note (scope alignment):**
> The previous revision of this document described an aspirational “universal ingestion engine”
> (DOCX/PPTX/XLSX/HTML + Docling/PaddleOCR). This repository (per `README.md`, `pyproject.toml`,
> and `src/mmrag_converter/*`) currently implements a **local-only converter for PDF and EPUB**
> using **PyMuPDF + (optional) Surya + Tesseract**.
>
> This document defines **verifiable, testable requirements for the current codebase**.

---

## 1. Purpose

Convert documents into retrieval-friendly artifacts (JSON/JSONL + optional images) suitable for
multimodal RAG pipelines, while preserving section context (“breadcrumb”) and enabling quality
regression checks.

---

## 2. In-scope / out-of-scope

### 2.1 In-scope input formats

- **PDF**: born-digital, scanned, and mixed PDFs
- **EPUB**: extracted in spine order (XHTML items treated as “pages”)

### 2.2 Experimental / best-effort input formats

The CLI currently attempts to open any file supported by **PyMuPDF** (examples in this repo
include `.docx`, `.pptx`, `.xlsx`, `.html`). These formats are treated as:

- **Best-effort only**: the same PDF-oriented heuristics are applied.
- **No stability guarantees**: output quality/structure MAY change between versions.

If these formats are intended as first-class support, they MUST be promoted into §2.1 with
format-specific acceptance criteria and tests.

### 2.3 Out-of-scope (explicitly NOT implemented as dedicated pipelines)

- Format-specific DOCX/PPTX/XLSX/HTML pipelines (style mapping, slide semantics, table semantics)
- “Single universal ingestion.jsonl schema” with table/image chunks embedded as first-class
  modalities
- Document Intelligence engines such as Docling
- PaddleOCR

If/when these are implemented, they MUST be introduced as a new version of this document with
clear acceptance criteria.

---

## 3. Definitions / glossary

- **workdir**: Output directory containing per-document subfolders
- **doc_id**: Stable identifier derived from input filename stem (used as workdir folder name)
- **page_number**: 1-based page index; for EPUB it refers to spine item index + 1
- **scanned-like page**: A page whose extracted digital text length is below `min_chars_for_digital`
- **breadcrumb_path**: Active hierarchy context (H1/H2/H3) inherited by paragraphs and chunks

---

## 4. Functional requirements

### 4.1 CLI availability

- **REQ-CLI-1**: The project MUST provide a CLI entrypoint `mmrag-convert`.
- **REQ-CLI-2**: The CLI MUST support at minimum the commands documented in `README.md`:
  `inspect`, `render-pages`, `extract-text`, `ocr-fallback`, `detect-doc-type`, `analyze-structure`,
  `chunk`, `convert`, `evaluate`, `regression`.

### 4.2 Document inspection

- **REQ-INSPECT-1**: `inspect <doc>` MUST output: path, doc_id, page count, and any
  available metadata (PDF metadata or EPUB OPF metadata).

### 4.3 Page rendering (PDF only)

- **REQ-RENDER-1**: `render-pages <pdf> -w <workdir> --dpi <dpi>` MUST render each PDF page to a
  PNG under `workdir/pages/<doc_id>/pNNN.png`.
- **REQ-RENDER-2**: Rendering MUST be an explicit opt-in step. The end-to-end `convert` pipeline
  MUST NOT save full-page PNGs by default.

### 4.4 Text extraction (PDF + EPUB)

- **REQ-TEXT-1**: `extract-text <doc> -w <workdir>` MUST create
  `workdir/text/<doc_id>/pages_raw.jsonl`.
- **REQ-TEXT-1b**: `extract-text` MUST create or refresh `workdir/text/<doc_id>/doc_meta.json`.
- **REQ-TEXT-2**: For PDF, extraction MUST attempt layout-aware reading order reconstruction:
  - Prefer Surya layout ordering when Surya is available.
  - Otherwise fall back to a deterministic heuristic ordering.
- **REQ-TEXT-3**: For EPUB, extraction MUST follow **spine order** and convert XHTML to text while
  preserving paragraph-ish boundaries using newlines.
- **REQ-TEXT-4**: Each output row MUST include `is_scanned_like` based on
  `min_chars_for_digital`.

### 4.5 OCR fallback (PDF only)

- **REQ-OCR-1**: `ocr-fallback <pdf> -w <workdir> --lang <lang>` MUST read
  `pages_raw.jsonl` and write `pages_with_ocr.jsonl` to the same text directory.
- **REQ-OCR-2**: OCR MUST only be applied to rows flagged `is_scanned_like=true`.
- **REQ-OCR-3**: The OCR step MUST avoid penalizing separator/blank pages by marking them as
  `is_blank_page=true` and excluding them from OCR coverage metrics.

### 4.6 Persistent hierarchy state (context inheritance)

- **REQ-STATE-1**: The system MUST maintain a persistent `ContextState` per `doc_id` containing:
  `current_h1`, `current_h2`, `current_h3`, `breadcrumb_path`, `current_page`.
- **REQ-STATE-2**: When headings exist in a document, each paragraph block MUST have a non-empty
  `breadcrumb_path` (at least a root).
- **REQ-STATE-3**: Chunk outputs MUST inherit `breadcrumb_path` from their source blocks.

### 4.7 Structure analysis (blocks)

- **REQ-STRUCT-1**: `analyze-structure <doc> -w <workdir>` MUST write
  `blocks_structured.jsonl`.
- **REQ-STRUCT-2**: The output MUST contain `heading` and `paragraph` block types.
- **REQ-STRUCT-3**: A best-effort `structure_report.txt` MUST be written alongside blocks to
  support human inspection of detected headings.

### 4.8 Chunking

- **REQ-CHUNK-1**: `chunk <doc> -w <workdir>` MUST write `chunks_text.jsonl`.
- **REQ-CHUNK-2**: The chunker MUST split at sentence boundaries whenever possible and MUST avoid
  mid-sentence splits as a first-class quality constraint.
- **REQ-CHUNK-3**: Chunks MUST include: `page_start`, `page_end`, `tokens_estimate`,
  `parent_heading`, `heading_level`, and `breadcrumb_path`.
- **REQ-CHUNK-4**: When `--dedup-exact-text` is enabled, chunks with identical text MUST be
  deduplicated.
- **REQ-CHUNK-5**: Contextual Overlap: Maintain a 10-15% token overlap between chunks within the same section.

### 4.9 Multimodal export (linking only)

- **REQ-MM-1**: If `export-multimodal` is enabled, `convert` MUST write
  `chunks_multimodal.jsonl`.
- **REQ-MM-2**: `chunks_multimodal.jsonl` MUST link each chunk to:
  - page images **if they already exist** under `workdir/pages/<doc_id>/`.
  - extracted figure images **if they exist** under `workdir/text/<doc_id>/figures/`.
- **REQ-MM-3**: The multimodal export MUST NOT require page images to exist; `page_images` may be
  empty.

### 4.10 Figure extraction (experimental)

- **REQ-FIG-1**: When enabled via `convert --extract-figures`, the converter MUST export cropped
  figure images under `workdir/text/<doc_id>/figures/` and write `figures.jsonl`.
- **REQ-FIG-2**: Figure extraction MUST avoid exporting full-page images by default by applying
  conservative area-ratio thresholds.
- **REQ-FIG-3**: Figure filenames MUST follow:
  `<doc_id>_<page_number:03d>_Figure_<index:02d>.png`.

### 4.11 Quality evaluation and regression

- **REQ-QA-1**: `evaluate <doc> -w <workdir>` MUST write `quality_report.json`.
- **REQ-QA-2**: `regression` MUST iterate over all PDFs/EPUBs in a directory and exit with
  non-zero status if thresholds are violated.

---

## 5. Output artifacts and schemas (normative)

All JSON/JSONL MUST be UTF-8.

### 5.1 `doc_meta.json`

Written under `workdir/text/<doc_id>/doc_meta.json`.

```json
{
  "doc_id": "<string>",
  "source_path": "<string>",
  "pdf_metadata": {},
  "profile": {
    "doc_type": "digital|scanned",
    "doc_domain": "academic|manual|book",
    "scanned_page_ratio": 0.0,
    "signals": {"total_pages": 0, "scanned_like_pages": 0},
    "decided_by": "auto|override|mixed",
    "version": 1
  }
}
```

### 5.2 `pages_raw.jsonl`

One JSON object per page/spine item:

```json
{
  "doc_id": "<string>",
  "page_index": 0,
  "page_number": 1,
  "raw_text": "<string>",
  "is_scanned_like": false
}
```

### 5.3 `pages_with_ocr.jsonl` (PDF only, optional)

Same as `pages_raw.jsonl` plus:

```json
{
  "from_ocr": false,
  "is_blank_page": false
}
```

### 5.4 `blocks_structured.jsonl`

```json
{
  "doc_id": "<string>",
  "page_index": 0,
  "page_number": 1,
  "block_id": "<string>",
  "block_type": "heading|paragraph",
  "heading_level": 1,
  "text": "<string>",
  "parent_heading": "<string>|null",
  "breadcrumb_path": ["<string>"]
}
```

### 5.5 `chunks_text.jsonl`

```json
{
  "doc_id": "<string>",
  "chunk_id": "<string>",
  "page_start": 1,
  "page_end": 1,
  "text": "<string>",
  "tokens_estimate": 123,
  "parent_heading": "<string>|null",
  "heading_level": 1,
  "breadcrumb_path": ["<string>"],
  "modality": "text"
}
```

### 5.6 `chunks_multimodal.jsonl`

```json
{
  "doc_id": "<string>",
  "chunk_id": "<string>",
  "page_start": 1,
  "page_end": 2,
  "text": "<string>",
  "tokens_estimate": 123,
  "parent_heading": "<string>|null",
  "heading_level": 1,
  "breadcrumb_path": ["<string>"],
  "modality": "text",
  "page_images": ["/abs/or/rel/path/to/p001.png"],
  "figures": [
    {
      "figure_id": "<string>",
      "page_number": 1,
      "bbox": [0.0, 0.0, 10.0, 10.0],
      "image_path": "<string>"
    }
  ]
}
```

### 5.7 `quality_report.json`

The report MUST include at least:

- `heading_noise_ratio`
- `chunks_duplicate_ratio`
- `ocr_coverage`
- `chunks_bad_boundary_ratio`

---

## 6. Non-functional requirements

- **NFR-1 (Offline)**: Conversion MUST not require network access.
- **NFR-2 (Determinism)**: For a fixed input, output ordering MUST be deterministic
  (same pages -> same JSONL line order) within a single version.
- **NFR-3 (Token estimate)**: `tokens_estimate` MUST be documented as a heuristic and MUST NOT be
  treated as a strict tokenizer output.

---

## 7. Verification

Each requirement MUST have at least one of the following verification methods:

- Unit tests (`tests/test_*.py`)
- CLI smoke tests using sample docs under `examples/sample_docs/`
- `regression` command thresholds

### 7.1 Requirement → verification matrix

| Requirement | Verification method (current) |
| --- | --- |
| REQ-CLI-1 / REQ-CLI-2 | `mmrag-convert --help` output; smoke tests (manual) |
| REQ-INSPECT-1 | CLI smoke test: `mmrag-convert inspect <doc>` |
| REQ-RENDER-1 / REQ-RENDER-2 | CLI smoke test: `render-pages`; check `convert` does not create `workdir/pages/*` by default |
| REQ-TEXT-1 / REQ-TEXT-1b / REQ-TEXT-4 | CLI smoke test: `extract-text`; presence + schema keys in `pages_raw.jsonl` and `doc_meta.json` |
| REQ-TEXT-2 | Integration smoke test on multi-column PDF; optional Surya run if installed |
| REQ-TEXT-3 | Unit/integration: `tests/test_epub_structure.py` + EPUB smoke conversion |
| REQ-OCR-1..3 | Integration smoke test on synthetic scanned PDF + `quality_report.json` OCR coverage |
| REQ-STATE-1..3 | Unit tests: `tests/test_state_machine.py` |
| REQ-STRUCT-1..3 | CLI smoke test: `analyze-structure`; presence of `structure_report.txt` |
| REQ-CHUNK-1..4 | Unit tests: `tests/test_chunker.py` + smoke conversions |
| REQ-MM-1..3 | CLI smoke test: `convert --export-multimodal` with/without rendered pages |
| REQ-FIG-1..3 | Integration smoke test: `convert --extract-figures` (small PDF) |
| REQ-QA-1 / REQ-QA-2 | CLI smoke test: `evaluate` and `regression` on a small corpus |

---

## 8. Known limitations (current)

- No DOCX/PPTX/XLSX/HTML support.
- No table extraction pipeline.
- No “unified ingestion.jsonl” that merges text+images+tables into a single schema.
- Page image rendering is an explicit separate step; `convert` links to images if they exist.
