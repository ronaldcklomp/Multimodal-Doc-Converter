# src/mmrag_converter/cli.py
from __future__ import annotations

import json
from pathlib import Path

import typer

from .ocr_engine import apply_ocr_fallback
from .page_renderer import render_pdf_to_images
from .text_extractor import extract_text_per_page
from .chunker import chunk_blocks_to_jsonl
from .multimodal_export import export_multimodal_chunks
from .figure_extractor import extract_figures_from_pdf
from .structure_analyzer import analyze_text_structure
from .pdf_loader import get_pdf_info
from .quality_metrics import evaluate_workdir, report_to_json

from .doc_profile import (
    DocDomain,
    DocType,
    DocProfile,
    detect_doc_profile_from_pages,
    load_doc_profile,
    load_pages_jsonl,
    save_doc_profile,
)

app = typer.Typer(
    help="Multimodal RAG document converter (PDF -> images + raw text/ocr).")


def _should_run_ocr_for_convert(
    *,
    doc_path: Path,
    profile: DocProfile,
    ocr_scanned_pages: bool,
) -> bool:
    """Centralized OCR gating for the convert pipeline.

    Rationale:
    - PyMuPDF can open/render some non-PDF formats (HTML/Office). Running OCR on
      those tends to inject garbage text and should not be the default.
    - OCR is expensive; if there are no scanned-like pages we skip it.
    """

    # OCR is PDF-only by default.
    if doc_path.suffix.lower() != ".pdf":
        return False

    scanned_like_pages = int((profile.signals or {}).get("scanned_like_pages", 0))
    if scanned_like_pages <= 0:
        return False

    # Always OCR fully-scanned docs. Optionally OCR mixed PDFs.
    return profile.doc_type == DocType.scanned or ocr_scanned_pages


def _ensure_exists(path: Path) -> None:
    if not path.exists():
        raise typer.BadParameter(f"File not found: {path}")


def _path_arg(path: str) -> Path:
    return Path(path)


@app.command()
def inspect(
    pdf: str = typer.Argument(..., help="Pad naar de PDF"),
):
    """
    Toon basisinformatie over een PDF (doc_id, aantal pagina's, metadata).
    """
    pdf_path = _path_arg(pdf)
    info = get_pdf_info(pdf_path)

    typer.echo(f"PDF:      {info.path}")
    typer.echo(f"doc_id:   {info.doc_id}")
    typer.echo(f"pages:    {info.num_pages}")
    if info.metadata:
        typer.echo("metadata:")
        for k, v in info.metadata.items():
            if v:
                typer.echo(f"  {k}: {v}")


@app.command("render-pages")
def render_pages(
    pdf: str = typer.Argument(..., help="Pad naar de PDF"),
    workdir: str = typer.Option(
        "workdir",
        "--workdir",
        "-w",
        help="Werkdirectory voor tussenresultaten",
    ),
    dpi: int = typer.Option(
        200,
        "--dpi",
        help="Render-resolutie in DPI (default 200)",
    ),
):
    """
    Render de PDF naar PNG pagina-afbeeldingen.
    """
    pdf_path = _path_arg(pdf)
    workdir_path = _path_arg(workdir)

    results = render_pdf_to_images(pdf_path, workdir_path, dpi=dpi)

    typer.echo(f"Gerenderde pagina's voor {pdf_path}:")
    for page_index, image_path in results:
        typer.echo(f"  page {page_index + 1:03d} -> {image_path}")


@app.command("extract-text")
def extract_text_cmd(
    pdf: str = typer.Argument(..., help="Pad naar de PDF"),
    workdir: str = typer.Option(
        "workdir",
        "--workdir",
        "-w",
        help="Werkdirectory voor tussenresultaten",
    ),
    min_chars_for_digital: int = typer.Option(
        30,
        "--min-chars-for-digital",
        help=(
            "Min. aantal karakters om een pagina als 'digitale tekst' "
            "te beschouwen."),
    ),
):
    """
    Extraheer ruwe tekst per pagina en schrijf JSONL in workdir.
    """
    pdf_path = _path_arg(pdf)
    workdir_path = _path_arg(workdir)

    out_path = extract_text_per_page(
        pdf_path=pdf_path,
        workdir=workdir_path,
        min_chars_for_digital=min_chars_for_digital,
    )

    # Create/refresh doc metadata. This is useful even if the user later
    # overrides via --doc-type/--doc-domain.
    info = get_pdf_info(pdf_path)
    text_dir = workdir_path / "text" / info.doc_id
    pages = load_pages_jsonl(out_path)
    profile = detect_doc_profile_from_pages(
        pages,
        pdf_metadata=info.metadata,
    )
    save_doc_profile(
        text_dir=text_dir,
        doc_id=info.doc_id,
        source_path=str(pdf_path),
        pdf_metadata=info.metadata,
        profile=profile,
    )

    typer.echo(f"Ruwe tekst per pagina opgeslagen in: {out_path}")


@app.command("ocr-fallback")
def ocr_fallback_cmd(
    pdf: str = typer.Argument(..., help="Pad naar de PDF"),
    workdir: str = typer.Option(
        "workdir",
        "--workdir",
        "-w",
        help="Werkdirectory voor tussenresultaten",
    ),
    lang: str = typer.Option(
        "eng",
        "--lang",
        help="Tesseract taalcode, bijvoorbeeld 'eng', 'nld', 'deu'",
    ),
):
    """
    Voer OCR uit op pagina's die als 'gescand' zijn gemarkeerd
    in pages_raw.jsonl en schrijf een nieuw JSONL-bestand
    met OCR-tekst.
    """
    pdf_path = Path(pdf)
    workdir_path = Path(workdir)

    out_path = apply_ocr_fallback(pdf_path=pdf_path,
                                  workdir=workdir_path, lang=lang)
    typer.echo(f"OCR-fallback resultaat opgeslagen in: {out_path}")


@app.command("convert")
def convert_cmd(
    pdf: str = typer.Argument(..., help="Pad naar de PDF"),
    workdir: str = typer.Option(
        "workdir",
        "--workdir",
        "-w",
        help="Werkdirectory voor tussenresultaten",
    ),
    dpi: int = typer.Option(
        200,
        "--dpi",
        help="Render-resolutie in DPI (default 200)",
    ),
    min_chars_for_digital: int = typer.Option(
        30,
        "--min-chars-for-digital",
        help=(
            "Min. aantal karakters om een pagina als 'digitale tekst' "
            "te beschouwen."
        ),
    ),
    ocr_lang: str = typer.Option(
        "eng",
        "--ocr-lang",
        help="Tesseract taalcode, bijvoorbeeld 'eng', 'nld', 'deu'",
    ),
    max_tokens: int = typer.Option(
        400,
        "--max-tokens",
        help="Maximaal geschatte tokens per chunk.",
    ),
    min_tokens: int = typer.Option(
        30,
        "--min-tokens",
        help="Minimum estimated tokens per chunk (tiny chunks may be dropped).",
    ),
    dedup_exact_text: bool = typer.Option(
        True,
        "--dedup-exact-text/--no-dedup-exact-text",
        help="Drop exact duplicate chunk texts.",
    ),
    export_multimodal: bool = typer.Option(
        True,
        "--export-multimodal/--no-export-multimodal",
        help=(
            "Write chunks_multimodal.jsonl linking chunks to page images "
            "(when images exist)."
        ),
    ),
    doc_type: DocType = typer.Option(
        DocType.auto,
        "--doc-type",
        help="Override physical doc type: auto|digital|scanned",
        case_sensitive=False,
    ),
    doc_domain: DocDomain = typer.Option(
        DocDomain.auto,
        "--doc-domain",
        help="Override doc domain: auto|academic|manual|book",
        case_sensitive=False,
    ),
    render_images: bool | None = typer.Option(
        None,
        "--render-images/--no-render-images",
        help=(
            "(Deprecated) Render full-page PNGs to workdir/pages. "
            "Disabled by default to comply with REQUIREMENTS.md REQ-M1."
        ),
    ),
    ocr_scanned_pages: bool = typer.Option(
        True,
        "--ocr-scanned-pages/--no-ocr-scanned-pages",
        help=(
            "(PDF only) Run OCR for pages marked as scanned-like (low/empty text). "
            "OCR is only executed when scanned-like pages are detected. "
            "Recommended for mixed PDFs that have a few image-only pages."
        ),
    ),
    extract_figures: bool = typer.Option(
        False,
        "--extract-figures/--no-extract-figures",
        help=(
            "Experimental: extract figure images (cropped from rendered pages) "
            "and write figures.jsonl + figures/*.png under the text dir."
        ),
    ),
) -> None:
    """End-to-end pipeline for RAG ingestion.

    Steps:
    1) inspect (metadata)
    2) render-pages
    3) extract-text
    4) detect-doc-type (auto + optional overrides) -> doc_meta.json
    5) OCR fallback (if scanned)
    6) analyze-structure (domain-aware)
    7) chunk (domain-aware)
    """

    pdf_path = _path_arg(pdf)
    _ensure_exists(pdf_path)
    workdir_path = _path_arg(workdir)

    info = get_pdf_info(pdf_path)
    text_dir = workdir_path / "text" / info.doc_id

    # 1) render (disabled by default)
    is_epub = pdf_path.suffix.lower() == ".epub"
    effective_render = (not is_epub) if render_images is None else render_images
    if effective_render and (not is_epub):
        typer.echo(
            "Skipping full-page PNG rendering (REQ-M1). "
            "Use `mmrag-convert render-pages` if you explicitly need full pages."
        )

    # 2) extract text
    pages_raw_path = extract_text_per_page(
        pdf_path=pdf_path,
        workdir=workdir_path,
        min_chars_for_digital=min_chars_for_digital,
    )
    pages = load_pages_jsonl(pages_raw_path)

    # 3) detect / override profile
    profile = detect_doc_profile_from_pages(
        pages,
        pdf_metadata=info.metadata,
        doc_type_override=doc_type,
        doc_domain_override=doc_domain,
    )
    save_doc_profile(
        text_dir=text_dir,
        doc_id=info.doc_id,
        source_path=str(pdf_path),
        pdf_metadata=info.metadata,
        profile=profile,
    )

    # 4) OCR fallback
    in_path = pages_raw_path

    # For EPUB there are no page images / no OCR.
    if not is_epub:
        should_ocr = _should_run_ocr_for_convert(
            doc_path=pdf_path,
            profile=profile,
            ocr_scanned_pages=ocr_scanned_pages,
        )
        if should_ocr:
            ocr_path = apply_ocr_fallback(
                pdf_path=pdf_path,
                workdir=workdir_path,
                lang=ocr_lang,
            )
            in_path = ocr_path

    # 5) structure
    blocks_path = text_dir / "blocks_structured.jsonl"
    analyze_text_structure(
        in_path=in_path,
        out_path=blocks_path,
        doc_domain=profile.doc_domain,
    )

    # 6) chunk
    chunks_path = text_dir / "chunks_text.jsonl"
    chunk_blocks_to_jsonl(
        blocks_path=blocks_path,
        out_path=chunks_path,
        max_tokens=max_tokens,
        min_tokens=min_tokens,
        dedup_exact_text=dedup_exact_text,
        doc_domain=profile.doc_domain,
    )

    # 7) figure extraction (optional)
    # NOTE: must happen before multimodal export so that chunks_multimodal
    # can attach figures from figures.jsonl.
    if extract_figures and (not is_epub):
        _ = extract_figures_from_pdf(
            pdf_path=pdf_path,
            workdir=workdir_path,
        )

    # 8) multimodal export (optional)
    out_mm: Path | None = None
    if export_multimodal:
        pages_dir = workdir_path / "pages" / info.doc_id
        out_mm = text_dir / "chunks_multimodal.jsonl"
        export_multimodal_chunks(
            chunks_path=chunks_path,
            pages_dir=pages_dir,
            out_path=out_mm,
        )

    typer.echo(f"doc_id: {info.doc_id}")
    typer.echo(f"profile: type={profile.doc_type}, domain={profile.doc_domain}")
    typer.echo(f"pages_raw: {pages_raw_path}")
    if in_path != pages_raw_path:
        typer.echo(f"pages_with_ocr: {in_path}")
    typer.echo(f"blocks: {blocks_path}")
    typer.echo(f"chunks: {chunks_path}")
    if out_mm is not None:
        typer.echo(f"chunks_multimodal: {out_mm}")


@app.command("detect-doc-type")
def detect_doc_type_cmd(
    pdf: str = typer.Argument(..., help="Pad naar de PDF"),
    workdir: str = typer.Option(
        "workdir",
        "--workdir",
        "-w",
        help="Werkdirectory voor tussenresultaten",
    ),
    doc_type: DocType = typer.Option(
        DocType.auto,
        "--doc-type",
        help="Override physical doc type: auto|digital|scanned",
        case_sensitive=False,
    ),
    doc_domain: DocDomain = typer.Option(
        DocDomain.auto,
        "--doc-domain",
        help="Override doc domain: auto|academic|manual|book",
        case_sensitive=False,
    ),
):
    """Detect (or override) document profile and persist to doc_meta.json.

    Requires pages_raw.jsonl (run `extract-text` first).
    """
    pdf_path = _path_arg(pdf)
    workdir_path = _path_arg(workdir)
    info = get_pdf_info(pdf_path)
    text_dir = workdir_path / "text" / info.doc_id
    in_raw = text_dir / "pages_raw.jsonl"
    if not in_raw.exists():
        typer.echo(
            f"pages_raw.jsonl niet gevonden: {in_raw}. Run eerst extract-text."
        )
        raise typer.Exit(code=1)

    pages = load_pages_jsonl(in_raw)
    profile = detect_doc_profile_from_pages(
        pages,
        pdf_metadata=info.metadata,
        doc_type_override=doc_type,
        doc_domain_override=doc_domain,
    )
    meta_path = save_doc_profile(
        text_dir=text_dir,
        doc_id=info.doc_id,
        source_path=str(pdf_path),
        pdf_metadata=info.metadata,
        profile=profile,
    )

    typer.echo(f"doc_type:   {profile.doc_type}")
    typer.echo(f"doc_domain: {profile.doc_domain}")
    typer.echo(f"scanned_page_ratio: {profile.scanned_page_ratio:.2f}")
    typer.echo(f"saved: {meta_path}")


@app.command("analyze-structure")
def analyze_structure_cmd(
    pdf: str = typer.Argument(
        ...,
        help="Pad naar de PDF.",
    ),
    workdir: str = typer.Option(
        "workdir",
        "--workdir",
        "-w",
        help="Werkdirectory voor tussenresultaten.",
    ),
    doc_type: DocType = typer.Option(
        DocType.auto,
        "--doc-type",
        help="Override physical doc type: auto|digital|scanned",
        case_sensitive=False,
    ),
    doc_domain: DocDomain = typer.Option(
        DocDomain.auto,
        "--doc-domain",
        help="Override doc domain: auto|academic|manual|book",
        case_sensitive=False,
    ),
) -> None:
    """
    Analyseer headings en paragrafen en schrijf blokken-JSONL.
    """
    pdf_path = _path_arg(pdf)
    workdir_path = _path_arg(workdir)

    info = get_pdf_info(pdf_path)
    text_dir = workdir_path / "text" / info.doc_id

    # gebruik pages_with_ocr.jsonl als die bestaat, anders pages_raw.jsonl
    in_ocr = text_dir / "pages_with_ocr.jsonl"
    in_raw = text_dir / "pages_raw.jsonl"

    # Determine profile (auto / override)
    # If doc_meta.json exists, we respect that. Otherwise we auto-detect.
    pages_for_profile = load_pages_jsonl(in_raw) if in_raw.exists() else []
    prof_existing = load_doc_profile(text_dir)
    prof = detect_doc_profile_from_pages(
        pages_for_profile,
        pdf_metadata=info.metadata,
        doc_type_override=doc_type,
        doc_domain_override=doc_domain,
    )
    # Persist if missing or if user provided an override.
    if (
        prof_existing is None
        or doc_type != DocType.auto
        or doc_domain != DocDomain.auto
    ):
        save_doc_profile(
            text_dir=text_dir,
            doc_id=info.doc_id,
            source_path=str(pdf_path),
            pdf_metadata=info.metadata,
            profile=prof,
        )

    # Prefer OCR text when the document is scanned.
    if prof.doc_type == DocType.scanned and in_ocr.exists():
        in_path = in_ocr
    else:
        in_path = in_ocr if in_ocr.exists() else in_raw

    out_path = text_dir / "blocks_structured.jsonl"

    result = analyze_text_structure(
        in_path=in_path,
        out_path=out_path,
        doc_domain=prof.doc_domain,
    )
    typer.echo(f"Structuur-blokken opgeslagen in: {result}")


@app.command("chunk")
def chunk_cmd(
    pdf: str = typer.Argument(
        ...,
        help="Pad naar de PDF.",
    ),
    workdir: str = typer.Option(
        "workdir",
        "--workdir",
        "-w",
        help="Werkdirectory voor tussenresultaten.",
    ),
    max_tokens: int = typer.Option(
        400,
        "--max-tokens",
        help="Maximaal geschatte tokens per chunk.",
    ),
    min_tokens: int = typer.Option(
        30,
        "--min-tokens",
        help="Minimum estimated tokens per chunk (tiny chunks may be dropped).",
    ),
    dedup_exact_text: bool = typer.Option(
        True,
        "--dedup-exact-text/--no-dedup-exact-text",
        help="Drop exact duplicate chunk texts.",
    ),
    doc_domain: DocDomain = typer.Option(
        DocDomain.auto,
        "--doc-domain",
        help="Override doc domain: auto|academic|manual|book",
        case_sensitive=False,
    ),
) -> None:
    """
    Maak RAG-vriendelijke tekstchunks uit blocks_structured.jsonl.
    """
    pdf_path = _path_arg(pdf)
    workdir_path = _path_arg(workdir)

    info = get_pdf_info(pdf_path)
    text_dir = workdir_path / "text" / info.doc_id

    blocks_path = text_dir / "blocks_structured.jsonl"
    if not blocks_path.exists():
        typer.echo(f"blocks_structured.jsonl niet gevonden: {blocks_path}")
        raise typer.Exit(code=1)

    out_path = text_dir / "chunks_text.jsonl"

    prof = load_doc_profile(text_dir)
    # Fall back to book-ish behavior if doc_meta.json is missing.
    effective_domain = prof.doc_domain if prof is not None else DocDomain.book
    if doc_domain != DocDomain.auto:
        effective_domain = doc_domain

    result = chunk_blocks_to_jsonl(
        blocks_path=blocks_path,
        out_path=out_path,
        max_tokens=max_tokens,
        min_tokens=min_tokens,
        dedup_exact_text=dedup_exact_text,
        doc_domain=effective_domain,
    )
    typer.echo(f"Text-chunks opgeslagen in: {result}")


@app.command("evaluate")
def evaluate_cmd(
    doc: str = typer.Argument(..., help="PDF/EPUB path"),
    workdir: str = typer.Option(
        "workdir_eval",
        "--workdir",
        "-w",
        help="Workdir used for conversion and report output",
    ),
    doc_domain: DocDomain = typer.Option(
        DocDomain.auto,
        "--doc-domain",
        help="Override doc domain: auto|academic|manual|book",
        case_sensitive=False,
    ),
    max_tokens: int = typer.Option(300, "--max-tokens"),
    min_tokens: int = typer.Option(30, "--min-tokens"),
) -> None:
    """Run `convert` and produce a `quality_report.json` in the text dir."""

    doc_path = _path_arg(doc)
    _ensure_exists(doc_path)
    workdir_path = _path_arg(workdir)

    # Run conversion with safe defaults for evaluation.
    convert_cmd(
        pdf=str(doc_path),
        workdir=str(workdir_path),
        dpi=200,
        min_chars_for_digital=30,
        ocr_lang="eng",
        max_tokens=max_tokens,
        min_tokens=min_tokens,
        dedup_exact_text=True,
        export_multimodal=True,
        doc_type=DocType.auto,
        doc_domain=doc_domain,
        render_images=None,
        ocr_scanned_pages=True,
    )

    info = get_pdf_info(doc_path)
    text_dir = workdir_path / "text" / info.doc_id
    report = evaluate_workdir(
        doc_id=info.doc_id,
        source_path=str(doc_path),
        text_dir=text_dir,
        min_tokens=min_tokens,
    )
    out_path = text_dir / "quality_report.json"
    out_path.write_text(report_to_json(report), encoding="utf-8")
    typer.echo(str(out_path))


@app.command("regression")
def regression_cmd(
    docs_dir: str = typer.Option(
        "examples/sample_docs",
        "--docs-dir",
        help="Directory containing PDF/EPUB corpus for regression.",
    ),
    workdir: str = typer.Option(
        "workdir_regression",
        "--workdir",
        "-w",
        help="Where to place per-doc conversion outputs and reports.",
    ),
    max_heading_noise: float = typer.Option(
        0.10,
        "--max-heading-noise",
        help="Max ratio of junk headings (0-1).",
    ),
    max_duplicate_ratio: float = typer.Option(
        0.01,
        "--max-duplicate-ratio",
        help="Max ratio of exact duplicate chunks (0-1).",
    ),
    min_ocr_coverage: float = typer.Option(
        0.90,
        "--min-ocr-coverage",
        help="Min OCR coverage for scanned-like pages (0-1).",
    ),
    max_bad_boundary_ratio: float = typer.Option(
        0.01,
        "--max-bad-boundary-ratio",
        help=(
            "Max ratio of likely bad chunk boundaries (mid-sentence splits). "
            "0.01 means ~1 per 100 chunks."
        ),
    ),
    max_tokens: int = typer.Option(300, "--max-tokens"),
    min_tokens: int = typer.Option(30, "--min-tokens"),
) -> None:
    """Run evaluation across a corpus and fail (exit!=0) if thresholds are violated."""

    docs_path = _path_arg(docs_dir)
    if not docs_path.exists() or not docs_path.is_dir():
        raise typer.BadParameter(f"docs-dir is not a directory: {docs_path}")

    workdir_path = _path_arg(workdir)
    workdir_path.mkdir(parents=True, exist_ok=True)

    candidates = sorted(
        [
            p
            for p in docs_path.iterdir()
            if p.is_file() and p.suffix.lower() in {".pdf", ".epub"}
        ]
    )
    if not candidates:
        raise typer.BadParameter(f"No PDF/EPUB files found in: {docs_path}")

    failures: list[str] = []
    for doc_path in candidates:
        # Use a doc-specific workdir to keep reports separate.
        sub = workdir_path / doc_path.stem
        sub.mkdir(parents=True, exist_ok=True)

        # Evaluate writes quality_report.json.
        evaluate_cmd(
            doc=str(doc_path),
            workdir=str(sub),
            doc_domain=DocDomain.auto,
            max_tokens=max_tokens,
            min_tokens=min_tokens,
        )

        info = get_pdf_info(doc_path)
        report_path = sub / "text" / info.doc_id / "quality_report.json"
        report_data = json.loads(report_path.read_text(encoding="utf-8"))

        doc_type = str(report_data.get("doc_type", "auto"))
        noise = float(report_data.get("heading_noise_ratio", 0.0))
        dups = float(report_data.get("chunks_duplicate_ratio", 0.0))
        below = int(report_data.get("chunks_below_min_tokens", 0))
        scanned_like = int(report_data.get("scanned_like_pages", 0))
        ocr_cov = float(report_data.get("ocr_coverage", 1.0))
        bad_boundary_ratio = float(report_data.get("chunks_bad_boundary_ratio", 0.0))

        if noise > max_heading_noise:
            failures.append(
                f"{doc_path.name}: heading_noise_ratio {noise:.3f} > {max_heading_noise:.3f}"
            )
        if dups > max_duplicate_ratio:
            failures.append(
                f"{doc_path.name}: duplicate_ratio {dups:.3f} > {max_duplicate_ratio:.3f}"
            )
        if below != 0:
            failures.append(f"{doc_path.name}: chunks_below_min_tokens {below} != 0")
        # Only enforce OCR coverage for physically scanned documents.
        # For "digital" docs, scanned-like pages can be covers / illustrations
        # where OCR is noisy and may be filtered out.
        if doc_type == "scanned" and scanned_like > 0 and ocr_cov < min_ocr_coverage:
            failures.append(
                f"{doc_path.name}: ocr_coverage {ocr_cov:.3f} < {min_ocr_coverage:.3f}"
            )
        if bad_boundary_ratio > max_bad_boundary_ratio:
            failures.append(
                (
                    f"{doc_path.name}: bad_boundary_ratio "
                    f"{bad_boundary_ratio:.3f} > {max_bad_boundary_ratio:.3f}"
                )
            )

    if failures:
        typer.echo("Regression failed:\n" + "\n".join(f"- {f}" for f in failures))
        raise typer.Exit(code=1)

    typer.echo(f"Regression OK: {len(candidates)} docs")


if __name__ == "__main__":
    app()
