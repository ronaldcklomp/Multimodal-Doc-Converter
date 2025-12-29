# Multimodal Document Converter — Requirements Specification (v1.2.0)  
**Precision-Grade Specification for LLM Code Generation**  
*Authored by Principal Multimodal RAG Engineer • Date: 2025-12-28*  
**CORE PRINCIPLE: Zero tolerance for semantic ambiguity, data corruption, or unverifiable outputs. Every requirement MUST be machine-enforceable.**

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
|--------|-------------------|-------------------|-------------------------------|  
| **PDF** | `NIST-PDF-1.7-SUITE` + `ARXIV-10K` (scanned/digital hybrids) | ≥99.9% block-level text accuracy | Preserve logical reading order |
| **EPUB** | `EPUBTEST.ORG-3.2-CERTIFIED` + `PROJECT-GUTENBERG-500` | 100% spine-order fidelity | Respect NCX/Navigation Doc |  
| **DOCX** | `OFFICE-VALIDATION-CORPUS-v1` (10K synthetic documents) | ≥99.5% style-to-heading mapping accuracy | Map styles to semantic hierarchy |  
| **PPTX** | `SLIDE-VALIDATION-SUITE-v1` (5K synthetic presentations) | ≥99.5% slide-coherence preservation | Treat slides as atomic sections |  
| **XLSX** | `SPREADSHEET-TESTBED-v1` (3K synthetic workbooks) | ≥99.0% table structure integrity | Preserve sheet relationships |  
| **HTML** | `W3C-VALIDATION-CORPUS-v1` (8K synthetic pages) | ≥99.5% DOM-to-visual order fidelity | Honor CSS visual flow |  

#### ⚠️ **EXPERIMENTAL/BEST-EFFORT INPUT FORMATS**  

- **PyMuPDF-supported formats** (e.g., `.docx`, `.pptx`, `.xlsx`, `.html` via PyMuPDF) are treated as:  
  - **Best-effort only**: PDF-oriented heuristics applied without format-specific optimization  
  - **No stability guarantees**: Output quality/structure MAY change between versions  
  - **No quality thresholds**: Validation metrics not enforced  
  - **Explicit warning**: CLI MUST output `"[WARNING] Best-effort conversion. For production use, use dedicated format parser."`  

#### ⚠️ **FORMAT-SPECIFIC EXCLUSIONS (NO SUPPORT)**  

| Format | Excluded Elements | Recovery Action |  
|--------|-------------------|----------------|  
| **DOCX** | VBA macros, ActiveX controls, Custom XML parts | Strip with warning; log stripped elements |  
| **PPTX** | Animation triggers, Embedded videos, 3D models | Convert to static images with metadata |  
| **XLSX** | Macros, PivotTable source data, External connections | Export values only; discard formulas |  
| **HTML** | `<script>`, `<iframe>`, Web Components | Sanitize with OWASP HTML Sanitizer; preserve text content |  

#### ⛔ **DEFERRED FEATURES (NOT IMPLEMENTED IN v1.2.0)**  

- **Table extraction as first-class entities** (beyond CSV exports for XLSX)  
- **Unified `ingestion.jsonl` schema** that merges text+images+tables into single schema  
- **Document Intelligence engines** (Docling, PaddleOCR) as primary processors  
- **Figure extraction without caption association**  
- *All deferred features MUST return explicit error:*  
  `"Feature unavailable in v1.2.0. Contribute validated parser via issue template."`  

---

## **2. Critical Definitions (Formal Semantics)**  

### 2.1 Core Terminology  

| Term | Definition |  
|------|------------|  
| `workdir` | Output directory containing per-document subfolders |  
| `doc_id` | Stable identifier: lowercase alphanumeric filename stem (a-z0-9_- only) |  
| `page_number` | 1-based page index; for EPUB refers to spine item index + 1 |  
| `scanned-like page` | Page where `1 - (shannon_entropy(extracted_text) / max_possible_entropy) > 0.85` OR `font_count(extracted_text) === 0` |  
| `breadcrumb_path` | Array of heading texts from root to immediate parent heading |  
| `physical context` | `[page_index, block_bbox]` where `block_bbox = [x0, y0, x1, y1]` normalized to page dimensions (0.0-1.0) |  

### 2.2 Context Integrity Protocol  

| Term | Formal Definition | Validation Rule |  
|------|-------------------|----------------|  
| `breadcrumb_path` | Array of heading texts from root to immediate parent heading. Empty ONLY if no headings exist on current page AND all prior pages. | `if (breadcrumb_path.length === 0) → is_rootless: true` |  
| `is_rootless` | Boolean indicating no valid semantic hierarchy. Requires physical context fallback. | `is_rootless === true` **iff** `no_headings_in_document === true` OR `block is in cover/colophon section` |  
| `physical_context` | `[page_index, block_bbox]` normalized coordinates | MUST be stored when `is_rootless: true` |  

### 2.3 Format-Specific Semantic Mapping Rules  

#### **PDF Semantic Hierarchy**  

| Native Element | RAG Context Mapping | Validation Rule |  
|----------------|---------------------|----------------|  
| Text blocks | Reading order determined by Surya (if available) or heuristic layout analysis | Must preserve logical flow across columns and around figures |  
| Detected headings | Heading levels inferred from font size hierarchy and position | Must follow W3C HTML5 sectioning rules |  
| Figure captions | `block_type: "figure_caption"` | MUST link to nearest figure block |  

#### **EPUB Semantic Hierarchy**  

| Native Element | RAG Context Mapping | Validation Rule |  
|----------------|---------------------|----------------|  
| Spine items | Treated as sequential pages | MUST follow publication spine order, not filename order |  
| NCX/Navigation | Document hierarchy source | MUST override visual heading detection when conflicts exist |  
| `<section>` tags | Section boundaries | MUST respect HTML5 sectioning content model |  

#### **DOCX Semantic Hierarchy**  

| Native Element | RAG Context Mapping | Validation Rule |  
|----------------|---------------------|----------------|  
| `Heading 1` style | `breadcrumb_path[0]` | MUST preserve style inheritance chain |  
| `Heading 2` style | `breadcrumb_path[1]` | Ignore custom styles not in `allowed_heading_styles.json` |  
| Table caption | `block_type: "table_caption"` | MUST link to next table block |  
| Footnote reference | `physical_context` only | Never inject into breadcrumb_path |  

#### **PPTX Semantic Hierarchy**  

| Native Element | RAG Context Mapping | Validation Rule |  
|----------------|---------------------|----------------|  
| Slide title | `heading_level: 1` | Treat as H1 even if font size < body text |  
| Section divider slide | `breadcrumb_path` root reset | MUST detect by `slide_layout.name` containing "Section" |  
| Notes pane | Separate block with `modality: "speaker_notes"` | Never merge with slide content |  
| Animation fragments | Flatten to single block | Preserve fragment order via `animation_sequence` metadata |  

#### **XLSX Semantic Hierarchy**  

| Native Element | RAG Context Mapping | Validation Rule |  
|----------------|---------------------|----------------|  
| Sheet name | `breadcrumb_path[0]` | Normalize names: `s/[^a-z0-9_-]/_/gi` |  
| Table title (above table) | `heading_level: 2` | Detect via adjacent merged cells with bold font |  
| PivotTable | `block_type: "pivot_table"` | Export as CSV + metadata; never rasterize |  
| Cell comment | `block_type: "annotation"` | Attach to parent cell block via `cell_ref` |  

#### **HTML Semantic Hierarchy**  

| Native Element | RAG Context Mapping | Validation Rule |  
|----------------|---------------------|----------------|  
| `<h1>`-`<h6>` | Native heading levels | Respect implicit sectioning from `<section>` tags |  
| ARIA landmarks | `breadcrumb_path` roots | `role="main"` → document root; `role="complementary"` → sidebar section |  
| CSS columns | Visual column order | Never follow DOM order if `column-count` > 1 |  
| Generated content (`::before`) | Exclude from text flow | Preserve in `css_generated_content.jsonl` with selector metadata |  

---

## **3. Non-Negotiable Functional Requirements**  

### 3.1 CLI Contract (REQ-CLI)  

- **REQ-CLI-1**: `mmrag-convert` MUST be POSIX-compliant. Windows paths auto-converted to POSIX relative paths.  
- **REQ-CLI-2**: The CLI MUST support these commands:  

  | Command | Required Parameters | Description |  
  |---------|---------------------|-------------|  
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
  |------|-----------|----------------|  
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

### 3.5 OCR Fallback (PDF Only) (REQ-OCR)  

- **REQ-OCR-1**: `ocr-fallback <pdf> -w <workdir> --lang <lang>` MUST read `pages_raw.jsonl` and write `pages_with_ocr.jsonl` to the same text directory.  
- **REQ-OCR-2**: OCR MUST only be applied to rows flagged `is_scanned_like=true`.  
- **REQ-OCR-3**: The OCR step MUST avoid penalizing separator/blank pages by marking them as `is_blank_page=true` and excluding them from OCR coverage metrics.  
- **REQ-OCR-4**: Language parameter MUST default to `eng` and support all languages available in Tesseract 5.3+.  

### 3.6 Format-Specific Extraction (REQ-FORMAT)  

- **REQ-FORMAT-1**: Dedicated extraction commands **MUST** exist: `extract-docx`, `extract-pptx`, `extract-xlsx`, `extract-html`  
- **REQ-FORMAT-2**: Native structure preservation:  
  - DOCX: Map Word styles to heading levels via `style_mappings.json` (version-controlled)  
  - PPTX: Preserve slide relationships via `slide_hierarchy.json`  
  - XLSX: Export tables as CSV with `table_<sheet>_<index>.csv` alongside text blocks  
  - HTML: Render CSS visual order using headless browser (Puppeteer) with *deterministic viewport* (1200×800)  
- **REQ-FORMAT-3**: Format-specific error handling (see Appendix B for complete error code mapping)  

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

- **REQ-CHUNK-1**: `chunk <doc> -w <workdir>` MUST write `chunks_text.jsonl`.  
- **REQ-CHUNK-2**: The chunker MUST split at sentence boundaries whenever possible and MUST avoid mid-sentence splits as a first-class quality constraint.  
- **REQ-CHUNK-3**: Chunks MUST include: `page_start`, `page_end`, `tokens_estimate`, `parent_heading`, `heading_level`, and `breadcrumb_path`.  
- **REQ-CHUNK-4**: When `--dedup-exact-text` is enabled, chunks with identical text MUST be deduplicated.  
- **REQ-CHUNK-5**: Contextual Overlap: Maintain overlap between chunks ONLY when:  
  `(current_block.heading_level === next_block.heading_level) AND`  
  `(semantic_section_id(current_block) === semantic_section_id(next_block))`  
  Overlap size: `min(64 tokens, 15% of smaller chunk)`  
- **REQ-CHUNK-6**: Hard Max Chunk Size: 512 tokens (cl100k_base) with overflow strategy:  

  ```python  
  if len(chunk) > 512:  
      split_at = last_valid_boundary_before(512 - overlap_window)  
      create_overflow_chunk(text[split_at:])  
  ```  

### 3.10 Multimodal Export (REQ-MM)  

- **REQ-MM-1**: If `--export-multimodal` is enabled, `convert` MUST write `chunks_multimodal.jsonl`.  
- **REQ-MM-2**: `chunks_multimodal.jsonl` MUST link each chunk to:  
  - page images if they already exist under `workdir/pages/<doc_id>/`  
  - extracted figure images if they exist under `workdir/text/<doc_id>/figures/`  
- **REQ-MM-3**: The multimodal export MUST NOT require page images to exist; `page_images` may be empty.  
- **REQ-MM-4**: Format-native assets **MUST** be exported with context (see section 3.6):  

  | Format | Asset Type | Export Path |  
  |--------|------------|-------------|  
  | DOCX | Embedded images | `figures/docx_<page_index>_<obj_id>.png` |  
  | PPTX | Slide images | `slides/pptx_<slide_number:03d>.png` |  
  | XLSX | Charts | `charts/xlsx_<sheet>_<chart_id>.png` |  
  | HTML | Canvas/SVG | `rendered/html_<element_id>.png` |  

### 3.11 Figure Extraction (Experimental) (REQ-FIG)  

- **REQ-FIG-1**: When enabled via `--extract-figures`, the converter MUST export cropped figure images under `workdir/text/<doc_id>/figures/` and write `figures.jsonl`.  
- **REQ-FIG-2**: Figure extraction MUST avoid exporting full-page images by default by applying area-ratio thresholds (<85% of page area).  
- **REQ-FIG-3**: Figure filenames MUST follow: `<doc_id>_<page_number:03d>_Figure_<index:02d>.png`.  
- **REQ-FIG-4**: Figure extraction is experimental and subject to change. MUST output warning: `"Figure extraction is experimental in v1.2.0"`.

### 3.12 Quality Evaluation and Regression (REQ-QA)  

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

### 3.13 Atomic Processing Protocol (REQ-ATOMIC)  

- **REQ-ATOMIC-1**: Every command operates within a transaction:  

  ```mermaid  
  graph LR  
  A[Start] --> B{Create temp_workdir}  
  B --> C[Process artifacts]  
  C --> D{Validation passed?}  
  D -->|Yes| E[Atomically move to final workdir]  
  D -->|No| F[Delete temp_workdir + log errors]  

  ```  
- **REQ-ATOMIC-2**: Output artifacts **MUST** include SHA-256 checksums in `workdir/checksums.sha256`.  

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

---

## **5. Non-Functional Requirements (Enforceable)**  

| ID | Requirement | Enforcement Mechanism |  
|----|-------------|------------------------|  
| NFR-1 | **Offline Operation** | Block all network calls at OS firewall level during tests |  
| NFR-2 | **Determinism** | `PYTHONHASHSEED=0` + sorted directory walks + fixed random seeds |  
| NFR-3 | **Token estimate** | `tokens_estimate` MUST use tiktoken `cl100k_base` with documented heuristic limitations |  
| NFR-4 | **Resource Safety** | Per-format memory caps (see section 5.1). Kill process if exceeded (SIGKILL). |  
| NFR-5 | **Audit Trail** | `workdir/audit_log.jsonl` with:<br>`{"timestamp": "ISO8601", "command": "...", "input_sha256": "...", "output_checksums": [...]}` |  

### 5.1 Format-Specific Resource Constraints  

| Format | Memory Cap | Time Cap | Failure Action |  
|--------|------------|----------|----------------|  
| PDF | 512MB | 60s/page | `ERR_RESOURCE_EXCEEDED` (Code 66) |  
| EPUB | 512MB | 30s/spine item | Process partial document with warning |  
| DOCX | 1GB | 120s | `ERR_RESOURCE_EXCEEDED` (Code 70) |  
| PPTX | 1.5GB | 180s | Render last valid slide + error block |  
| XLSX | 2GB | 300s | Export first 10K rows + warning |  
| HTML | 750MB | 90s | Skip frames/iframes; log skipped elements |  

---

## **6. Verification Protocol (100% Coverage Mandate)**  

### 6.1 Requirement → Verification Matrix  

| Requirement | Verification Method | Pass Criteria |  
|-------------|---------------------|---------------|  
| REQ-CLI-1/2 | `mmrag-convert --help` output; automated CLI tests | All documented commands available and functional |  
| REQ-INSPECT-1 | Unit test `test_inspect.py` | Correct metadata extraction for all formats |  
| REQ-RENDER-1/2 | Integration test `test_render.py` | Valid PNGs generated at specified DPI |  
| REQ-TEXT-1/2/3 | Integration tests per format | Text extraction matches reference corpus within thresholds |  
| REQ-OCR-1/2/3 | Test on `NIST-SCANNED-100` corpus | OCR confidence ≥0.9 on scanned blocks |  
| REQ-STATE-1/2/3 | Unit tests `test_context_state.py` | 100% of rootless blocks have physical_context |  
| REQ-STRUCT-1/2/3 | CLI test + manual validation | `structure_report.txt` accurately reflects document structure |  
| REQ-CHUNK-1/2/3 | Unit tests `test_chunker.py` | No mid-sentence splits; correct boundary handling |  
| REQ-MM-1/2/3 | Integration test `test_multimodal.py` | `modality_completeness_score` computed within ±0.001 tolerance |  
| REQ-QA-1/2 | CLI test on regression corpus | Correct failure on threshold violation |  
| REQ-ATOMIC-1/2 | Integration test with forced failures | No partial artifacts on failure; valid checksums on success |  

### 6.2 Validation Corpora  

- **PDF Layout Stress Tests**:  
  - 3-column text wrapping around images (LaTeX generated)  
  - Footnotes spanning page breaks  
  - Zero-point font text (invisible watermarking)  
- **EPUB Edge Cases**:  
  - Non-linear reading order (e.g., appendices before main text)  
  - XHTML fragments without `<body>` tags  
  - CSS-generated content (`::before` pseudo-elements)  
- **Office Format Adversarial Tests**:  
  - DOCX: Corrupted style hierarchies, nested tables with merged cells  
  - PPTX: Slides with animation fragments, master slide overrides  
  - XLSX: Circular references, cross-sheet formulas, PivotTables with grouped fields  
  - HTML: CSS multi-column layouts, ARIA landmark conflicts, mixed content  

### 6.3 Regression Thresholds (Configurable Defaults)  

```yaml  
# workdir/regression_thresholds.yaml  
max_heading_noise: 0.05  
min_ocr_coverage: 0.95  
max_duplicate_chunks: 0.01  
min_modality_completeness: 0.8  
format_specific:
  docx:
    min_style_consistency: 0.95
  pptx:
    min_slide_coherence: 0.95
  xlsx:
    min_table_integrity: 0.90
  html:
    min_css_fidelity: 0.95
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

---

## **Appendix B: Error Code Specification**  

| Code | Symbolic Name | Format Scope | Resolution Protocol |  
|------|---------------|--------------|---------------------|  
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

---

## **Appendix C: Known Limitations (v1.2.0)**  

- **Table semantics**: Tables are exported as text blocks or CSV (for XLSX) but lack semantic column/row relationships  
- **Complex layouts**: Multi-column text with interleaved figures may have imperfect reading order in PDFs  
- **EPUB non-linear documents**: Non-linear reading order (e.g., pop-up footnotes) may not preserve context correctly  
- **HTML dynamic content**: JavaScript-generated content is not executed or captured  
- **Document Intelligence**: No integration with specialized engines like Docling or PaddleOCR as primary processors  
- **Cross-references**: Hyperlinks and cross-references are not preserved as semantic relationships  

---

## **Engineering Imperatives for LLM Code Generation**  

1. **NO HEURISTICS WITHOUT FORMAL DEFINITIONS**  
   - Every threshold (e.g., `is_blank_page`) MUST use mathematically defined formulas from Appendix A.  
2. **CRYPTOGRAPHIC VERIFICATION IS MANDATORY**  
   - All outputs require SHA-256 checksums. No exceptions.  
3. **FAIL EARLY, FAIL LOUDLY**  
   - Return explicit error codes (Appendix B) within 100ms of detecting invalid input.  
4. **RESOURCE CONSTRAINTS ARE HARD BOUNDARIES**  
   - Enforce per-format memory caps via OS-level resource groups (Linux cgroups v2 / Windows Job Objects).  
5. **FORMAT ISOLATION PRINCIPLE**  
   - Implement format parsers as **separate modules** with strict input/output contracts  
   - Never share heuristics between formats (e.g., PDF column detection ≠ HTML CSS columns)  
6. **SEMANTIC FIDELITY OVER CONVENIENCE**  
   - When format semantics conflict with RAG requirements, **preserve original structure** and flag for human review  
7. **DEFERRED FEATURES ARE ABSENT FEATURES**  
   - Do not implement unified ingestion schema, table semantics, or Document Intelligence integration. Return error codes per Appendix B.  

> **"A DOCX heading isn't a PDF heading. A slide isn't a page. A cell isn't a paragraph. Respect the native semantics – or don't process the format at all."**  
> — *Multimodal RAG Engineering Manifesto, §3.2*  

**END OF SPECIFICATION**  
*This document is the authoritative specification for implementation. All validation corpora are synthetic test sets generated according to the defined adversarial cases. Cryptographic checksums for final implementation artifacts will be generated at build time.*  
*No external repositories or URLs are referenced in this specification. All resources are contained within the implementation package.*