# Multimodal Doc Converter

Local multimodal RAG document converter.

It ingests **PDF** (born-digital and scanned/mixed) and **EPUB**, and produces:

- Rendered page images (PNG) *(PDF only, optional)*
- Extracted per-page text (`pages_raw.jsonl`)
- OCR fallback for scanned-like pages (`pages_with_ocr.jsonl`) *(PDF only, optional)*
- Structured blocks (`blocks_structured.jsonl`) with headings/paragraphs
- Retrieval-friendly chunks (`chunks_text.jsonl`)
- Multimodal chunk export (`chunks_multimodal.jsonl`) linking each chunk to page images *(when images exist)*
- Quality metrics (`quality_report.json`) *(when using `evaluate` / `regression`)*

## Install

```bash
pip install -e .
```

## CLI

After installation you can run:

```bash
mmrag-convert --help
```

## Quick start

Use one of the included sample docs:

```bash
ls -1 examples/sample_docs
```

### End-to-end conversion (`convert`)

Example (PDF):

```bash
mmrag-convert convert "examples/sample_docs/AIOS LLM Agent Operating System.pdf" \
  --workdir workdir \
  --doc-domain academic \
  --max-tokens 300 \
  --min-tokens 30 \
  --dedup-exact-text \
  --ocr-scanned-pages \
  --export-multimodal
```

Example (EPUB):

```bash
mmrag-convert convert "examples/sample_docs/Seffer, David - KI En ChatGPT, Praktische Gids Voor Online Business Met Digitale Producten.epub" \
  --workdir workdir_epub \
  --doc-domain book \
  --max-tokens 300 \
  --min-tokens 30 \
  --dedup-exact-text
```

## Concepts

### `doc_id`

The converter derives a stable `doc_id` from the filename (and/or metadata). It is used as the folder name under the
workdir.

### Document profile (`doc_meta.json`)

`doc_meta.json` stores metadata and an auto-detected (or overridden) profile:

- `doc_type`: `digital|scanned` (physical/source nature)
- `doc_domain`: `academic|manual|book` (genre heuristics)
- signals like `scanned_like_pages` and `scanned_page_ratio`

You can always override via CLI flags.

## Commands

Run `mmrag-convert --help` to see all commands.

Below is a complete overview of commands and options (mirrors `--help`).

### `inspect`

Show basic metadata (works for PDF and EPUB):

```bash
mmrag-convert inspect <pdf-or-epub>
```

Options:

- `--help`

### `render-pages` (PDF)

Render page images as PNGs:

```bash
mmrag-convert render-pages <pdf> -w workdir --dpi 150
```

Options:

- `-w, --workdir` (default: `workdir`)

- `--dpi` (default: `150`, range: 72-600)

### `extract-text`

Extract text per page into `pages_raw.jsonl`:

```bash
mmrag-convert extract-text <pdf-or-epub> -w workdir
```

Options:

- `-w, --workdir` (default: `workdir`)
- `--min-chars-for-digital` (default: `30`) – pages below this are marked `is_scanned_like=true`

### `ocr-fallback` (PDF)

Run OCR for pages marked as scanned-like in `pages_raw.jsonl` (requires rendered images in `workdir/pages/<doc_id>`):

```bash
mmrag-convert ocr-fallback <pdf> -w workdir --lang eng
```

Options:

- `-w, --workdir` (default: `workdir`)
- `--lang` (default: `eng`)

### `detect-doc-type`

Compute and persist `doc_meta.json` (requires `pages_raw.jsonl` first):

```bash
mmrag-convert detect-doc-type <pdf-or-epub> -w workdir --doc-type auto --doc-domain auto
```

Options:

- `-w, --workdir` (default: `workdir`)
- `--doc-type` one of: `auto|digital|scanned`
- `--doc-domain` one of: `auto|academic|manual|book`

### `analyze-structure`

Convert `pages_raw.jsonl`/`pages_with_ocr.jsonl` into structured blocks:

```bash
mmrag-convert analyze-structure <pdf-or-epub> -w workdir --doc-type auto --doc-domain auto
```

Options:

- `-w, --workdir` (default: `workdir`)
- `--doc-type` one of: `auto|digital|scanned`
- `--doc-domain` one of: `auto|academic|manual|book`

### `chunk`

Chunk `blocks_structured.jsonl` into retrieval-friendly JSONL:

```bash
mmrag-convert chunk <pdf-or-epub> -w workdir --max-tokens 300 --min-tokens 30 --dedup-exact-text
```

Options:

- `-w, --workdir` (default: `workdir`)
- `--max-tokens` (default: `400`) – estimated token cap per chunk
- `--min-tokens` (default: `30`) – filter tiny chunks
- `--dedup-exact-text/--no-dedup-exact-text` (default: enabled)
- `--doc-domain` override: `auto|academic|manual|book`

### `convert`

Full end-to-end pipeline.

```bash
mmrag-convert convert <pdf-or-epub> -w workdir [options]
```

Options:

- `-w, --workdir` (default: `workdir`)
- `--dpi` (default: `150`, range: 72-600) *(PDF rendering)*
- `--min-chars-for-digital` (default: `30`)
- `--ocr-lang` (default: `eng`)
- `--max-tokens` (default: `400`)
- `--min-tokens` (default: `30`)
- `--dedup-exact-text/--no-dedup-exact-text` (default: enabled)
- `--export-multimodal/--no-export-multimodal` (default: enabled)
- `--doc-type` override: `auto|digital|scanned`
- `--doc-domain` override: `auto|academic|manual|book`
- `--render-images/--no-render-images`
  - default: enabled for PDF
  - default: disabled for EPUB
- `--ocr-scanned-pages/--no-ocr-scanned-pages` (default: enabled)
  - (PDF only) runs OCR for pages flagged as scanned-like, even if the overall doc is “digital” (useful for mixed PDFs)
  - OCR is only executed when scanned-like pages are detected
  - garbage OCR is filtered and will not overwrite existing extracted text

### `evaluate`

Run `convert` with safe defaults and write `quality_report.json`:

```bash
mmrag-convert evaluate <pdf-or-epub> -w workdir_eval --max-tokens 300 --min-tokens 30
```

Options:

- `-w, --workdir` (default: `workdir_eval`)
- `--doc-domain` override: `auto|academic|manual|book`
- `--max-tokens` (default: `300`)
- `--min-tokens` (default: `30`)

### `regression`

Run `evaluate` across all `.pdf`/`.epub` files in a directory and fail if thresholds are violated:

```bash
mmrag-convert regression --docs-dir examples/sample_docs -w workdir_regression \
  --max-heading-noise 0.10 \
  --max-duplicate-ratio 0.01 \
  --min-ocr-coverage 0.90 \
  --max-tokens 300 \
  --min-tokens 30
```

Options:

- `--docs-dir` (default: `examples/sample_docs`)
- `-w, --workdir` (default: `workdir_regression`)
- `--max-heading-noise` (default: `0.10`)
- `--max-duplicate-ratio` (default: `0.01`)
- `--min-ocr-coverage` (default: `0.90`) *(applies only when scanned-like pages exist)*

Note: `min_ocr_coverage` is only enforced for documents classified as `doc_type=scanned`.
- `--max-tokens` (default: `300`)
- `--min-tokens` (default: `30`)

## Useful subcommands (quick recipes)

```bash
mmrag-convert inspect <pdf-or-epub>
mmrag-convert render-pages <pdf> -w workdir --dpi 150
mmrag-convert extract-text <pdf-or-epub> -w workdir
mmrag-convert detect-doc-type <pdf-or-epub> -w workdir --doc-domain book
mmrag-convert analyze-structure <pdf-or-epub> -w workdir
mmrag-convert chunk <pdf-or-epub> -w workdir --max-tokens 300 --min-tokens 30
```

## Output layout

Given `doc_id = small_manual`:

```tree
workdir/
  pages/
    small_manual/
      p001.png ...
  text/
    small_manual/
      doc_meta.json
      pages_raw.jsonl
      pages_with_ocr.jsonl
      blocks_structured.jsonl
      chunks_text.jsonl
      chunks_multimodal.jsonl
      quality_report.json
```

## Development

Run unit tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'
```

## Notes for vector database ingestion

- `chunks_text.jsonl` is a good default for text embedding.
- By default the converter does **not** save full-page PNGs (see REQUIREMENTS.md REQ-M1). Use `render-pages` explicitly
  if you want them.
- Token counts are **estimates** (word-based heuristic). Always enforce hard limits at embedding time if required.
