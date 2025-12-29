# Multimodal Document Converter — Requirements Specification (v1.3.1)

**Precision-Grade Specification for LLM Code Generation**  
*Authored by Principal Multimodal RAG Engineer • Date: 2025-12-29*  
**CORE PRINCIPLE: Zero tolerance for semantic ambiguity, data corruption, or unverifiable outputs. Every requirement MUST be machine-enforceable.**

Note that versions mentioned in this document are most likely old versions and used for illustration. For all software packets here goes: install latest version when possible, ony defer when dependencies demand differently.

---

## **1. Purpose & Scope**

### 1.1 Core Mission  

Convert documents to **verifiably correct**, **context-integrity-preserving** artifacts for multimodal RAG pipelines. Output must be:  

- **Semantically lossless**: No hallucinated hierarchy or orphaned multimodal references  
- **Byte-reproducible**: Identical inputs → identical outputs across environments (within same version)  
- **Audit-trail complete**: Every decision point logged with cryptographic verification  

### 1.2 Strict Scope Boundaries

#### ✅ **FIRST-CLASS SUPPORT (MUST PASS 99.9% VALIDATION)**  

| Format | Validation Corpus | Failure Threshold | Native Semantics Requirement |  
| -------- | ------------------- | ------------------- | ------------------------------- |  
| **PDF** | `NIST-PDF-1.7-SUITE` + `ARXIV-10K` + `PUBLAYNET-5K` | ≥99.9% block-level text accuracy | Preserve logical reading order using Surya layout engine |  
| **EPUB** | `EPUBTEST.ORG-3.2-CERTIFIED` + `PROJECT-GUTENBERG-500` | 100% spine-order fidelity | Respect NCX/Navigation Doc |  
| **DOCX/PPTX/XLSX** | `DOCling-OFFICE-CORPUS-v1` (15K documents) | ≥99.7% structural fidelity | Native parsing via Docling engine with table/figure semantics |  
| **HTML** | `W3C-VALIDATION-CORPUS-v1` (8K synthetic pages) + `COMMONCRAWL-SNAP-1K` | ≥99.5% DOM-to-visual order fidelity | Honor CSS visual flow via headless rendering |  

#### ⚠️ **FORMAT-SPECIFIC EXCLUSIONS (NO SUPPORT)**  

| Format | Excluded Elements | Recovery Action |  
| -------- | ------------------- | ---------------- |  
| **DOCX** | VBA macros, ActiveX controls, Custom XML parts | Strip with warning; log stripped elements |  
| **PPTX** | Animation triggers, Embedded videos, 3D models | Convert to static images with metadata |  
| **XLSX** | Macros, PivotTable source data, External connections | Export values only; discard formulas |  
| **HTML** | `<script>`, `<iframe>`, Web Components | Sanitize with OWASP HTML Sanitizer; preserve text content |  

#### ⛔ **DEFERRED FEATURES (NOT IMPLEMENTED IN v1.3.1)**

- **Document Intelligence engines** (PaddleOCR as primary processor)  
- *All deferred features MUST return explicit error:*  
  `"Feature unavailable in v1.3.1. Contribute validated parser via issue template."`  

---

## **2. Critical Definitions (Formal Semantics)**

### 2.1 Core Terminology  

| Term | Definition |  
| ------ | ------------ |  
| `workdir` | Output directory containing per-document subfolders |  
| `doc_id` | Stable identifier: lowercase alphanumeric filename stem (a-z0-9_- only) |  
| `page_number` | 1-based page index; for EPUB refers to spine item index + 1 |  
| `scanned-like page` | Page where `1 - (shannon_entropy(extracted_text) / max_possible_entropy) > 0.85` OR `font_count(extracted_text) === 0` |  
| `breadcrumb_path` | Array of heading texts from root to immediate parent heading |  
| `physical context` | `[page_index, block_bbox]` where `block_bbox = [x0, y0, x1, y1]` normalized to page dimensions (0.0-1.0) |  

### 2.2 Context Integrity Protocol

| Term | Formal Definition | Validation Rule |  
| ------ | ------------------- | ---------------- |  
| `breadcrumb_path` | Array of heading texts from root to immediate parent heading. Empty ONLY if no headings exist on current page AND all prior pages. | `if (breadcrumb_path.length === 0) → is_rootless: true` |  
| `is_rootless` | Boolean indicating no valid semantic hierarchy. Requires physical context fallback. | `is_rootless === true` **iff** `no_headings_in_document === true` OR `block is in cover/colophon section` |  
| `physical_context` | `[page_index, block_bbox]` normalized coordinates | MUST be stored when `is_rootless: true` |  

### 2.3 Format-Specific Semantic Mapping Rules

#### **Office Formats (DOCX/PPTX/XLSX) - Docling Engine**  

| Native Element | RAG Context Mapping | Validation Rule |  
| ---------------- | --------------------- | ---------------- |  
| Tables | `block_type: "table"` with `table_cells` array | MUST preserve row/column relationships; export as Markdown + CSV |  
| Figures with captions | Linked pair: `block_type: "figure"` + `block_type: "figure_caption"` | MUST associate via spatial proximity (≤5% page height gap) OR explicit reference |  
| Charts | `block_type: "chart"` with `chart_data` (JSON) + raster image | MUST extract underlying data series when available |  
| Slide groups | Hierarchical sections based on slide master | Section headers MUST reset breadcrumb_path |  

#### **PDF Layout Semantics (Surya Engine)**

| Native Element | RAG Context Mapping | Validation Rule |  
| ---------------- | --------------------- | ---------------- |  
| Columns | Visual column order | MUST follow Surya's column detection with ≥99% accuracy on PubLayNet |  
| Sidebars/footnotes | Physical context groups | MUST preserve proximity relationships via bounding box analysis |  
| Mathematical content | `block_type: "equation"` | MUST preserve LaTeX representation when detected |  

---

## **3. Non-Negotiable Functional Requirements**

### 3.1 CLI Contract (REQ-CLI)  

- **REQ-CLI-1**: `mmrag-convert` MUST be POSIX-compliant. Windows paths auto-converted to POSIX relative paths.  
- **REQ-CLI-2**: The CLI MUST support these commands:  

  | Command | Required Parameters | Description |  
  | --------- | --------------------- | ------------- |  
  | `inspect` | `<doc>` | Output path, doc_id, page count, and available metadata |  
  | `render-pages` | `<pdf> -w <workdir> --dpi <dpi>` | Render PDF pages to PNGs |  
  | `extract-text` | `<doc> -w <workdir>` | Create `pages_raw.jsonl` and `doc_meta.json` |  
  | `ocr-fallback` | `<pdf> -w <workdir> --lang <lang>` | Apply OCR to scanned-like pages |  
  | `detect-doc-type` | `<doc> -w <workdir>` | Determine document type/profile |  
  | `analyze-structure` | `<doc> -w <workdir>` | Write `blocks_structured.jsonl` and `structure_report.txt` |  
  | `chunk` | `<doc> -w <workdir>` | Write `chunks_text.jsonl` |  
  | `convert` | `<doc> -w <workdir>` | End-to-end conversion to optimized artifacts |  
  | `evaluate` | `<doc> -w <workdir>` | Write `quality_report.json` |  
  | `regression` | `<dir> -w <workdir>` | Run quality evaluation on corpus, fail on threshold violation |  

- **REQ-CLI-3**: Subcommands **MUST** fail with explicit exit codes:  

  | Code | Condition | Recovery Action |  
  | ------ | ----------- | ---------------- |  
  | 64 | Invalid input format | `stderr: "Unsupported format. Supported: PDF, EPUB, DOCX, PPTX, XLSX, HTML"` |  
  | 65 | Encrypted PDF without `--password` | `stderr: "Encrypted PDF. Use --password=<file>"` |  
  | 66 | Resource limit exceeded | `stderr: "Memory cap exceeded. See format-specific limits in documentation."` |  
  | 67 | Checksum mismatch on input | `audit_log.jsonl` entry with `input_sha256` mismatch |  
  | 68-74 | Format-specific errors | See Appendix B for detailed error codes |  

### 3.2 Document Inspection (REQ-INSPECT)  

- **REQ-INSPECT-1**: `inspect <doc>` MUST output: path, doc_id, page count, and any available metadata (PDF metadata or EPUB OPF metadata).  
- **REQ-INSPECT-2**: For Office formats, MUST report document properties (author, creation date, revision count).  

### 3.3 Page Rendering (PDF Only) (REQ-RENDER)  

- **REQ-RENDER-1**: `render-pages <pdf> -w <workdir> --dpi <dpi>` MUST render each PDF page to a PNG under `workdir/pages/<doc_id>/pNNN.png`.  
- **REQ-RENDER-2**: DPI parameter MUST accept values 72-600, defaulting to 150.  
- **REQ-RENDER-3**: Rendering MUST be an explicit opt-in step. The end-to-end `convert` pipeline MUST NOT save full-page PNGs by default.  

### 3.4 Text Extraction (REQ-TEXT)  

- **REQ-TEXT-1**: `extract-text <doc> -w <workdir>` MUST create `workdir/text/<doc_id>/pages_raw.jsonl`.  
- **REQ-TEXT-1b**: `extract-text` MUST create or refresh `workdir/text/<doc_id>/doc_meta.json`.  
- **REQ-TEXT-2**: For PDF, extraction MUST attempt layout-aware reading order reconstruction:  
  - Prefer Surya layout ordering when Surya is available (log: `"Using Surya layout analysis"`).  
  - Otherwise fall back to deterministic heuristic ordering (log: `"Using heuristic layout analysis"`).  
- **REQ-TEXT-3**: For EPUB, extraction MUST follow spine order and convert XHTML to text while preserving paragraph boundaries using newlines.  
- **REQ-TEXT-4**: Each output row MUST include `is_scanned_like` based on `scanned-like page` definition.  
- **REQ-TEXT-5**: For Office/HTML formats, extraction MUST respect format-specific semantic mapping rules in section 2.3.
- **REQ-TEXT-6**: For PDFs, MUST log layout engine usage:  
  `"Using Surya layout analysis (v1.5.0)"` OR `"Using fallback heuristic layout analysis"`  
- **REQ-TEXT-7**: For Office formats, MUST use Docling engine exclusively (no PyMuPDF fallback). Log:  
  `"Using Docling engine (v1.5.2) for native structure preservation"`  

### 3.5 OCR Fallback (REQ-OCR)

- **REQ-OCR-1**: `ocr-fallback <pdf> -w <workdir> --lang <lang>` MUST read `pages_raw.jsonl` and write `pages_with_ocr.jsonl` to the same text directory.  
- **REQ-OCR-2**: OCR MUST only be applied to rows flagged `is_scanned_like=true`.  
- **REQ-OCR-3**: The OCR step MUST avoid penalizing separator/blank pages by marking them as `is_blank_page=true` and excluding them from OCR coverage metrics.  
- **REQ-OCR-4**: Language parameter MUST default to `auto` and support all languages available in Tesseract 5.3+.  
- **REQ-OCR-5**: Mandatory preprocessing MUST be applied before OCR:  

  ```python  
  preprocess_image(image):  
      deskew(angle_threshold=0.5°)  
      binarize(adaptive_method="gaussian", block_size=15)  
      denoise(sigma=1.2)  
      deskew_output = deskew(preprocessed_image)  
  ```  

- **REQ-OCR-6**: Language handling:  
  - Auto-detect languages using Surya's language classifier (90+ languages)  
  - Support multi-language documents via `--lang auto` (default)  
  - Manual override via comma-separated list: `--lang eng,spa,fra`  
- **REQ-OCR-7**: Quality metrics MUST include OHRBench-inspired evaluation:  

  ```json  
  "ocr_quality_metrics": {  
    "character_accuracy": 0.98,  
    "word_accuracy": 0.95,  
    "structural_preservation": 0.92  // Measures layout integrity post-OCR  
  }  
  ```  

### 3.6 Format-Specific Extraction (REQ-FORMAT)

- **REQ-FORMAT-1**: Dedicated extraction commands **MUST** exist: `extract-docx`, `extract-pptx`, `extract-xlsx`, `extract-html`  
- **REQ-FORMAT-2**: Native structure preservation:  
  - DOCX: Map Word styles to heading levels via `style_mappings.json` (version-controlled)  
  - PPTX: Preserve slide relationships via `slide_hierarchy.json`  
  - XLSX: Export tables as CSV with `table_<sheet>_<index>.csv` alongside text blocks  
  - HTML: Render CSS visual order using headless browser (Puppeteer) with *deterministic viewport* (1200×800)  
- **REQ-FORMAT-3**: Format-specific error handling (see Appendix B for complete error code mapping)
- **REQ-FORMAT-4**: Docling engine integration:  
  - MUST process Office formats through Docling with ≥99.7% structural fidelity  
  - MUST preserve table semantics as first-class entities (not flattened text)  
  - MUST export Docling's native confidence scores per structural element  
- **REQ-FORMAT-5**: Surya engine integration for PDF layout:  
  - MUST use Surya when available for PDF layout analysis (fallback to heuristics only when Surya unavailable)  
  - MUST export Surya's block confidence scores in `blocks_structured.jsonl`

### 3.7 Persistent Hierarchy State (REQ-STATE)  

- **REQ-STATE-1**: The system MUST maintain a persistent `ContextState` per `doc_id` containing: `current_h1`, `current_h2`, `current_h3`, `breadcrumb_path`, `current_page`.  
- **REQ-STATE-2**: When headings exist in a document, each paragraph block MUST have non-empty `breadcrumb_path` OR explicitly marked as `is_rootless: true` with `physical_context`.  
- **REQ-STATE-3**: Chunk outputs MUST inherit `breadcrumb_path` from their source blocks OR preserve `physical_context` when rootless.  
- **REQ-STATE-4**: `ContextState` **MUST** persist as `workdir/state/<doc_id>.state.json` with format-specific metadata:  

  ```json  
  {  
    "version": 1,  
    "current_path": ["Chapter 1", "Methods"],  
    "page_states": {  
      "0": { "h1": "Abstract", "h2": null, "physical_bbox": [0.1,0.2,0.9,0.3] }  
    },  
    "is_rootless_document": false,  
    "format_metadata": {  
      "docx": {  
        "applied_styles": ["Heading1", "CustomHeading2"],  
        "style_source": "style_mappings_v2.json"  
      }  
    }  
  }  
  ```  

### 3.8 Structure Analysis (REQ-STRUCT)  

- **REQ-STRUCT-1**: `analyze-structure <doc> -w <workdir>` MUST write `blocks_structured.jsonl`.  
- **REQ-STRUCT-2**: The output MUST contain `heading` and `paragraph` block types. For tables and figures, MUST include appropriate block types.  
- **REQ-STRUCT-3**: A best-effort `structure_report.txt` MUST be written alongside blocks to support human inspection of detected headings and structure.  

### 3.9 Chunking (REQ-CHUNK)

- **REQ-CHUNK-1**: **Execution & Output**: The command `chunk <doc> -w <workdir>` MUST generate a `chunks_text.jsonl` file.
- **REQ-CHUNK-2**: **Metadata Requirements**: Each chunk entry MUST include: `page_start`, `page_end`, `tokens_estimate`, `parent_heading`, `heading_level`, and `breadcrumb_path`.
- **REQ-CHUNK-3**: **Deduplication**: When `--dedup-exact-text` is enabled, the engine MUST identify and remove chunks with 100% identical text content.
- **REQ-CHUNK-4**: **Semantic Partitioning Strategy**:
  - **Boundary Rule**: Splits MUST occur at sentence delimiters (`.`, `!`, `?`, `\n`). Mid-sentence splits are strictly prohibited.
  - **Standard Text**: Target size of 400-500 tokens with a **Hard Limit of 512 tokens** to ensure compatibility with standard embedding models.
  - **Structural Exceptions**: Markdown Tables, Code Blocks, and Figures+Captions MUST be treated as atomic units. If an atomic unit exceeds 512 tokens, it is permitted to extend to a **Hard Max of 1024 tokens** to preserve structural integrity. If still exceeding 1024, it must be split using "Header Repetition" logic.

- **REQ-CHUNK-5**: **Static Contextual Overlap**:

  - Overlap is ONLY permitted if: `(current_chunk.heading_level === next_chunk.heading_level)` AND `(semantic_section_id(current) === semantic_section_id(next))`.
  - **Base Size**: `min(64 tokens, 15% of the smaller chunk)`.

- **REQ-CHUNK-6**: **Dynamic Semantic Overlap (DSO)**:
  - **Trigger**: Active only when the `--semantic-overlap` flag is enabled.
  - **Model**: MUST utilize `sentence-transformers/all-MiniLM-L6-v2` (v2.2.2).
  - **Logic**:
    1. **Boundary Window**: Extract the last 3 sentences of the current chunk (Pre-Boundary) and the first 3 sentences of the proposed next chunk (Post-Boundary).
    2. **Similarity Check**: Calculate Cosine Similarity between the Pre-Boundary and Post-Boundary embeddings.
    3. **Dynamic Expansion**: If `similarity > 0.85`, increase the base overlap size by **50%**. Otherwise, retain the base size.

  - **Safety Constraint**: Dynamic overlap MUST NOT exceed **25%** of the total `target_chunk_size`.
  - **Fallback**: If the segment is too short to extract 3 sentences, the engine MUST default to the static overlap size defined in REQ-CHUNK-5.

### 3.10 Multimodal Export (REQ-MM)  

- **REQ-MM-1**: If `--export-multimodal` is enabled, `convert` MUST write `chunks_multimodal.jsonl`.  
- **REQ-MM-2**: `chunks_multimodal.jsonl` MUST link each chunk to:  
  - page images if they already exist under `workdir/pages/<doc_id>/`  
  - extracted figure images if they exist under `workdir/text/<doc_id>/figures/`  
- **REQ-MM-3**: The multimodal export MUST NOT require page images to exist; `page_images` may be empty.  
- **REQ-MM-4**: Format-native assets **MUST** be exported with context (see section 3.6):  

  | Format | Asset Type | Export Path |  
  | ------ | ---------- | ----------- |  
  | DOCX | Embedded images | `figures/docx_<page_index>_<obj_id>.png` |  
  | PPTX | Slide images | `slides/pptx_<slide_number:03d>.png` |  
  | XLSX | Charts | `charts/xlsx_<sheet>_<chart_id>.png` |  
  | HTML | Canvas/SVG | `rendered/html_<element_id>.png` |

- **REQ-MM-5**: Unified ingestion schema:  
  - `convert` command MUST output `ingestion.jsonl` as primary artifact  
  - Schema MUST integrate all modalities (text, tables, figures, charts) with explicit relationships:  

    ```json  
    {  
      "chunk_id": "doc123-chunk-456",  
      "modality_type": "text|table|figure|chart|equation",  
      "content": {  
        "text": "Raw text content",  
        "table": {"markdown": "| Header |", "csv_path": "tables/..."},  
        "figure": {"image_path": "figures/...", "caption": "Fig 1.1"}  
      },  
      "semantic_links": [  
        {"target_chunk": "doc123-chunk-789", "relationship": "caption_for"}  
      ],  
      "embedding_ready": true  // Precomputed for vector DB ingestion  
    }  
    ```  

- **REQ-MM-6**: Figure-caption association MUST be required (not experimental):  
  - Use Docling's native caption detection for Office formats  
  - For PDFs, use spatial proximity heuristic:  

    ```math  
    \text{caption\_distance} = \frac{\text{vertical\_gap between figure bbox and text block}}{\text{page height}} < 0.05  
    ```  

### 3.11 Figure Extraction (REQ-FIG)

- **REQ-FIG-1**: Figure extraction is REQUIRED for all formats when `--extract-figures` enabled. MUST output warning if disabled:  
  `"[WARNING] Figure extraction disabled. Multimodal RAG quality will be degraded."`  
- **REQ-FIG-2**: Caption linking is mandatory:  
  - Each figure MUST have associated caption text in metadata  
  - Unpaired figures MUST be flagged in `quality_report.json` as `unpaired_figures_ratio`  
- **REQ-FIG-3**: Format-native figure handling:

  | Format | Detection Method |  
  | ------ | ---------------- |  
  | PDF | Surya layout analysis + bbox clustering |  
  | DOCX/PPTX/XLSX | Docling structural analysis |  
  | HTML | Visual element clustering via Puppeteer |  

### 3.12 Quality Evaluation (REQ-QA)

- **REQ-QA-1**: `evaluate <doc> -w <workdir>` MUST write `quality_report.json` with metrics:  
  - `heading_noise_ratio`  
  - `chunks_duplicate_ratio`  
  - `ocr_coverage`  
  - `chunks_bad_boundary_ratio`  
  - Format-specific metrics as defined in Appendix A.1  
- **REQ-QA-2**: `regression` MUST iterate over all supported documents in a directory and exit with non-zero status if thresholds are violated.  
- **REQ-QA-3**: Threshold configuration MUST be loaded from `workdir/regression_thresholds.yaml` with defaults:  

  ```yaml
  max_heading_noise: 0.05
  min_ocr_coverage: 0.95
  max_duplicate_chunks: 0.01
  min_modality_completeness: 0.8
  ```

- **REQ-QA-4**: Mandatory OHRBench-inspired metrics:  

  ```json  
  "ocr_quality_metrics": {  
    "character_accuracy": 0.98,  
    "word_accuracy": 0.95,  
    "structural_preservation": 0.92  
  },  
  "multimodal_metrics": {  
    "figure_caption_pairing_ratio": 0.97,  
    "table_structure_preservation": 0.95  
  }  
  ```  

- **REQ-QA-5**: Unified schema validation:  
  - `ingestion.jsonl` MUST pass schema validation against `ingestion_schema_v1.3.json`  
  - Validation failures MUST halt pipeline with `ERR_SCHEMA_INVALID` (Code 75)  

---

## **4. Output Schemas (Normative & Verifiable)**

### 4.1 `doc_meta.json` (Mandatory Fields)  

```json
{  
  "doc_id": "string (alphanumeric, _- only)",  
  "source_path": "POSIX relative path from workdir root",  
  "format_type": "pdf|epub|docx|pptx|xlsx|html",
  "format_metadata": {},  // Format-specific metadata container
  "profile": {  
    "scanned_page_ratio": "float (0.0-1.0)",  
    "rootless_pages_ratio": "float (0.0-1.0)",  
    "validation": {  
      "input_sha256": "string",  
      "schema_version": "1.2.0"  
    }  
  }  
}  
```  

### 4.2 `pages_raw.jsonl`  

One JSON object per page/spine item/sheet:

```json  
{  
  "doc_id": "<string>",  
  "page_index": 0,  
  "page_number": 1,  
  "raw_text": "<string>",  
  "is_scanned_like": false
}  
```  

### 4.3 `pages_with_ocr.jsonl` (PDF only, optional)  

Same as `pages_raw.jsonl` plus:

```json  
{  
  "from_ocr": false,  
  "is_blank_page": false,
  "ocr_confidence": 0.95
}  
```  

### 4.4 `blocks_structured.jsonl`  

```json  
{  
  "doc_id": "<string>",  
  "page_index": 0,  
  "page_number": 1,  
  "block_id": "<string>",  
  "block_type": "heading|paragraph|table|figure|list",  
  "heading_level": 1,  
  "text": "<string>",  
  "parent_heading": "<string>|null",  
  "breadcrumb_path": ["<string>"],
  "physical_context": {  // REQUIRED when is_rootless:true  
    "page_index": 0,  
    "block_bbox": [0.12, 0.34, 0.56, 0.78]  // [x0, y0, x1, y1] normalized  
  },  
  "heading_confidence": 0.95,  // From structure analysis model
  "format_specific": {}  // Format-specific block metadata
}  
```  

### 4.5 `chunks_text.jsonl`  

```json  
{  
  "doc_id": "<string>",  
  "chunk_id": "<string>",  
  "page_start": 1,  
  "page_end": 1,  
  "text": "<string>",
  "source_blocks": ["<block_id1>", "<block_id2>"],  
  "tokens_estimate": 123,  
  "tokenizer_spec": "tiktoken/cl100k_base/v0.9.3",  // Hardcoded version
  "parent_heading": "<string>|null",  
  "heading_level": 1,  
  "breadcrumb_path": ["<string>"],
  "physical_context": {},  // When rootless
  "modality": "text",
  "overflow_chunk_id": "null | <chunk_id>",
  "source_format": "pdf|epub|docx|pptx|xlsx|html",
  "format_specific": {}  // Format-specific chunk metadata
}  
```  

### 4.6 `chunks_multimodal.jsonl`  

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
  "page_images": ["pages/<doc_id>/p001.png"],
  "figures": [  
    {  
      "figure_id": "<string>",  
      "page_number": 1,  
      "bbox": [0.0, 0.0, 10.0, 10.0],  
      "image_path": "<string>"  
    }  
  ],
  "asset_integrity": {
    "page_images": [{"path": "pages/...", "sha256": "a1b2c3..."}],
    "figures": [{"path": "figures/...", "sha256": "d4e5f6..."}]
  },
  "modality_completeness_score": 0.92,
  "source_format": "pdf|epub|docx|pptx|xlsx|html",
  "format_specific": {}
}  
```  

### 4.7 `quality_report.json`  

```json
{
  "doc_id": "<string>",
  "timestamp": "ISO8601",
  "metrics": {
    "heading_noise_ratio": 0.02,
    "chunks_duplicate_ratio": 0.01,
    "ocr_coverage": 0.98,
    "chunks_bad_boundary_ratio": 0.005,
    "format_specific": {
      "docx": {"style_consistency_ratio": 0.99},
      "pptx": {"slide_coherence_ratio": 0.98},
      "xlsx": {"table_integrity_score": 0.97},
      "html": {"css_fidelity_score": 0.99}
    }
  },
  "thresholds": {
    "max_heading_noise": 0.05,
    "min_ocr_coverage": 0.95,
    "max_duplicate_chunks": 0.01,
    "min_modality_completeness": 0.8
  },
  "passed": true
}
```

### 4.8 `ingestion.jsonl` (New Primary Output)

```json
{  
  "doc_id": "string",  
  "chunk_id": "string",  
  "modality_type": "text|table|figure|chart|equation",  
  "content": {  
    "text": "string | null",  
    "table": {  
      "markdown": "string",  
      "csv_path": "string",  
      "confidence": 0.95  
    } | null,  
    "figure": {  
      "image_path": "string",  
      "caption": "string",  
      "bbox": [0.1,0.2,0.3,0.4],  
      "confidence": 0.92  
    } | null  
  },  
  "semantic_links": [  
    {  
      "target_chunk": "string",  
      "relationship": "caption_for|data_source|related_equation"  
    }  
  ],  
  "embedding_ready": true,  
  "breadcrumb_path": ["string"],  
  "source_format": "pdf|epub|docx|pptx|xlsx|html",  
  "position_metadata": {  
    "page_start": 1,  
    "page_end": 1,  
    "physical_bbox": [0.1,0.2,0.3,0.4] | null  
  },  
  "quality_metadata": {  
    "confidence_score": 0.95,  
    "engine_used": "docling-v0.8.2 | surya-v1.5.0"  
  }  
}  
```  

### 4.9 Updated `chunks_multimodal.jsonl`

*(Modified to reference unified ingestion schema)*  

```json
{  
  "...",  
  "ingestion_schema_version": "1.3.0",  
  "primary_artifact": "ingestion.jsonl",  
  "legacy_chunks": ["chunks_text.jsonl"]  // For backward compatibility only  
}  
```  

*(All other schemas updated to include `modality_type` and `quality_metadata` fields)*  

---

## **5. Non-Functional Requirements (Enforceable)**

| ID | Requirement | Enforcement Mechanism |  
| -- | ----------- | --------------------- |  
| NFR-1 | **Offline Operation** | Block all network calls at OS firewall level during tests |  
| NFR-2 | **Determinism** | `PYTHONHASHSEED=0` + sorted directory walks + fixed random seeds |  
| NFR-3 | **Token estimate** | `tokens_estimate` MUST use tiktoken `cl100k_base` with documented heuristic limitations |  
| NFR-4 | **Resource Safety** | Per-format memory caps (see section 5.1). Kill process if exceeded (SIGKILL). |  
| NFR-5 | **Audit Trail** | `workdir/audit_log.jsonl` with: `{"timestamp": "ISO8601", "command": "...", "input_sha256": "...", "output_checksums": [...]}` |  

### 5.1 Enhanced Resource Constraints

| Format | Memory Cap | CPU Cap | Time Cap | Failure Action |  
| ------ | ---------- | ------- | -------- | -------------- |  
| PDF | 768MB | 2 vCPUs | 90s/page | `ERR_RESOURCE_EXCEEDED` |  
| DOCX/PPTX/XLSX | 1.5GB | 3 vCPUs | 150s | Fail with partial output + error report |  
| HTML | 1GB | 2 vCPUs | 120s | Skip complex elements; log skipped items |  
| **Global** | - | Max 4 vCPUs | - | Throttle via cgroups (Linux)/Job Objects (Windows) |  

### 5.2 Cryptographic Integrity Enforcement

- **REQ-CRYPTO-6**: All engine versions MUST be pinned and logged:

  ```json  
  "engine_versions": {  
    "docling": "2.66.0",
    "surya": "0.17.0",  
    "puppeteer": "24.34.0",  
    "tesseract": "5.5.2"
  }  
  ```  

---

## **6. Verification Protocol (100% Coverage Mandate)**

### 6.1 Requirement → Verification Matrix  

| Requirement | Verification Method | Pass Criteria |  
| ----------- | ------------------- | ------------- |  
| REQ-CLI-1/2/3 | `mmrag-convert --help` output; automated CLI tests | All documented commands available and functional |  
| REQ-INSPECT-1 | Unit test `test_inspect.py` | Correct metadata extraction for all formats |  
| REQ-RENDER-1/2/3 | Integration test `test_render.py` | Valid PNGs generated at specified DPI |  
| REQ-TEXT-1 to 7 | Integration tests per format | Text extraction matches reference corpus within thresholds |  
| REQ-OCR-1 to 7 | Test on `NIST-SCANNED-100` corpus | OCR confidence ≥0.9 on scanned blocks |  
| REQ-FORMAT-1 to 5 | T.B.D. | T.B.D. |
| REQ-STATE-1/2/3/4 | Unit tests `test_context_state.py` | 100% of rootless blocks have physical_context |  
| REQ-STRUCT-1/2/3 | CLI test + manual validation | `structure_report.txt` accurately reflects document structure |  
| REQ-CHUNK-1 to 7 | Unit tests `test_chunker.py` | No mid-sentence splits; correct boundary handling |  
| REQ-MM-1/2/3/4/5/6 | Integration test `test_multimodal.py` | `modality_completeness_score` computed within ±0.001 tolerance |  
| REQ-QA-1/2/3/4/5 | CLI test on regression corpus | Correct failure on threshold violation |  
| REQ-ATOMIC-1/2 | Integration test with forced failures | No partial artifacts on failure; valid checksums on success |  

### 6.2 Enhanced Validation Corpora

| Format | New Test Corpora | Adversarial Cases |  
| ------ | ---------------- | ----------------- |  
| **PDF** | `PUBLAYNET-5K` + `DOCVQA-TEST` | Complex layouts with tables spanning pages, handwritten annotations |  
| **Office** | `DOCling-VALIDATION-SUITE-v1` | Tables with merged cells across pages, figures with split captions |  
| **HTML** | `VISUAL-CRAWL-1K` | JavaScript-generated content, responsive layout shifts |  
| **OCR** | `OHRBench-REAL-SCANS` | Noisy scans with coffee stains, skewed documents, low-contrast text |  

### 6.3 Advanced Quality Thresholds

```yaml  
# workdir/regression_thresholds.yaml  
format_specific:  
  pdf:  
    min_surya_confidence: 0.90  
    max_layout_errors: 0.02  
  office:  
    min_docling_table_accuracy: 0.97  
    max_unpaired_figures: 0.03  
ocr:  
  min_character_accuracy: 0.95  
  min_structural_preservation: 0.85  
multimodal:  
  min_figure_caption_pairing: 0.95  
  min_table_structure_preservation: 0.90  
```  

---

## **Appendix A: Formal Metric Definitions**

### A.1 Core Metrics  

#### `heading_noise_ratio`  

```math  
\text{heading\_noise\_ratio} = 1 - \frac{\sum_{i=1}^{n} \text{valid\_heading}(i)}{n}  
```  

Where `valid_heading(i)` = 1 if heading `i` follows W3C sectioning rules, else 0.  

#### `chunks_bad_boundary_ratio`  

```math  
\text{bad\_boundary\_ratio} = \frac{\text{chunks with mid-sentence split AND no overflow chunk}}{\text{total chunks}}  
```  

*Mid-sentence split*: Last character not in `[.!?]` AND next chunk doesn't start with capital letter.  

#### `ocr_coverage`  

```math  
\text{ocr\_coverage} = \frac{\text{scanned\_pages with OCR confidence} \geq 0.8}{\text{total scanned\_pages}}  
```  

### A.2 Format-Specific Metrics  

#### **DOCX: `style_consistency_ratio`**  

```math  
\text{style\_consistency\_ratio} = \frac{\sum \text{valid\_heading\_mappings}}{\text{total\_headings}}  
```  

Where `valid_heading_mapping` = 1 if style maps to correct heading level per `style_mappings.json`, else 0.  

#### **PPTX: `slide_coherence_ratio`**  

```math  
\text{slide\_coherence\_ratio} = \frac{\text{slides with correct breadcrumb\_path}}{\text{total slides}}  
```  

*Correct breadcrumb_path*: Matches section hierarchy defined in slide master.  

#### **XLSX: `table_integrity_score`**  

```math  
\text{table\_integrity\_score} = \frac{\text{preserved cell relationships}}{\text{total cell relationships}}  
```  

*Cell relationship*: Adjacent cells in same logical table (detected via border continuity + header proximity).  

#### **HTML: `css_fidelity_score`**  

```math  
\text{css\_fidelity\_score} = \frac{\text{blocks in visual order}}{\text{total blocks}}  
```  

*Visual order*: Determined by Puppeteer's `getClientRects()` in normalized viewport.  

### A.3 New Multimodal Metrics

#### `figure_caption_pairing_ratio`

```math  
\text{pairing\_ratio} = \frac{\text{figures with correctly associated captions}}{\text{total figures}}  
```

*Correct association*: Caption text within 5% page height below figure bbox OR explicit reference in document structure.  

#### `table_structure_preservation`

```math
\text{table\_preservation} = \frac{\sum \text{correct cell relationships}}{\text{total expected relationships}}  
```

---

## **Appendix B: Error Code Specification**

| Code | Symbolic Name | Format Scope | Resolution Protocol |
| ---- | ------------- | ------------ | ------------------- |
| 64 | `ERR_UNSUPPORTED_FORMAT` | All | Reject input. Log supported formats. |
| 65 | `ERR_ENCRYPTED_PDF` | PDF | Require `--password` flag. Never prompt interactively. |
| 66 | `ERR_RESOURCE_EXCEEDED` | PDF/EPUB | Terminate process. Log page number + memory usage. |
| 67 | `ERR_CHECKSUM_MISMATCH` | All | Abort transaction. Preserve temp artifacts for forensics. |
| 68 | `ERR_STRUCTURE_INVALID` | All | Output `structure_validation.json` with invalid blocks flagged. |
| 69 | `ERR_EPUB_SPINE_ERROR` | EPUB | Fail conversion; log spine order issues |
| 70 | `ERR_DOCX_STYLE_CORRUPTION` | DOCX | Reject document; output `style_validation_report.json` |
| 71 | `ERR_PPTX_LAYOUT_MISSING` | PPTX | Use default layout; log missing references |
| 72 | `ERR_XLSX_CIRCULAR_REF` | XLSX | Break cycle at first detected loop; export partial data |
| 73 | `ERR_HTML_MIXED_CONTENT` | HTML | Block insecure resources; continue with sanitized DOM |
| 74 | `ERR_OFFICE_MACRO_DETECTED` | DOCX/PPTX/XLSX | Strip macros; log hash of stripped content |
| 75 | `ERR_SCHEMA_INVALID` | All | Halt pipeline; output `schema_validation_report.json` with failed fields |
| 76 | `ERR_ENGINE_UNAVAILABLE` | All | Require explicit engine install: `"Install Docling: pip install docling==0.8.2"` |
| 77 | `ERR_OCR_PREPROCESS_FAIL` | OCR | Skip preprocessing; apply OCR to raw image with warning |

---

## **Appendix C: Known Limitations (v1.3.0)**

- **Table semantics**: Tables are exported as text blocks or CSV (for XLSX) but lack semantic column/row relationships  
- **Complex layouts**: Multi-column text with interleaved figures may have imperfect reading order in PDFs  
- **EPUB non-linear documents**: Non-linear reading order (e.g., pop-up footnotes) may not preserve context correctly  
- **HTML dynamic content**: JavaScript-generated content is not executed or captured  
- **Document Intelligence**: No integration with specialized engines like Docling or PaddleOCR as primary processors  
- **Cross-references**: Hyperlinks and cross-references are not preserved as semantic relationships
- **Handwritten content**: OCR accuracy drops to 70-80% on cursive handwriting (not covered by OHRBench metrics)  
- **Dynamic HTML**: JavaScript-generated content after initial render is not captured  
- **3D models**: PPTX 3D models exported as static images without interactive capabilities  
- **Cross-document references**: Hyperlinks between documents not preserved as semantic relationships  
- **Voice annotations**: PPTX voice notes not extracted (treated as missing media)  

---

## **Engineering Imperatives for LLM Code Generation**

1. **ENGINE PINNING IS MANDATORY**  
   - Hardcode engine versions in requirements.txt, use DOCling's newest version, all other versions are of lower priority.
   - Fail immediately if wrong version detected: `"Incompatible engine version. Required: docling==2.66.0"`  
2. **SEMANTIC LINKS OVER MODALITY SPLITTING**  
   - Never separate figures from captions in chunking - treat as atomic semantic units  
   - Tables must preserve row/column relationships via `table_cells` array with coordinates  
3. **PREPROCESSING IS NON-NEGOTIABLE**  
   - OCR without deskew/binarization/denoise is considered invalid output  
   - Log preprocessing parameters in `quality_report.json` for auditability  
4. **UNIFIED SCHEMA IS PRIMARY OUTPUT**  
   - `ingestion.jsonl` replaces all legacy chunk files as the canonical output  
   - Legacy schemas (`chunks_text.jsonl`) maintained ONLY for backward compatibility with warnings  
5. **RESOURCE THROTTLING AT OS LEVEL**  
   - Implement CPU caps via Linux cgroups v2 `cpu.max` or Windows Job Objects `ActiveProcessLimit`  
   - Measure resource usage at 100ms intervals with kill switch at 110% of cap  

> **"Multimodal RAG fails when tables become text blobs and figures lose their captions. Preserve structure at all costs - or don't process the document at all."**  
> — *Multimodal RAG Engineering Manifesto, §4.1*
