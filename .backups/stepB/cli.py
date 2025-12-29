# src/mmrag_converter/cli.py
from __future__ import annotations

from pathlib import Path

import typer

from .ocr_engine import apply_ocr_fallback
from .page_renderer import render_pdf_to_images
from .text_extractor import extract_text_per_page
from .chunker import chunk_blocks_to_jsonl
from .structure_analyzer import analyze_text_structure
from .pdf_loader import get_pdf_info

from .doc_profile import (
    DocDomain,
    DocType,
    detect_doc_profile_from_pages,
    load_doc_profile,
    load_pages_jsonl,
    save_doc_profile,
)

app = typer.Typer(
    help="Multimodal RAG document converter (PDF -> images + raw text/ocr).")


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
            "Render page images to workdir/pages. Default: enabled for PDF, "
            "disabled for EPUB."
        ),
    ),
    ocr_scanned_pages: bool = typer.Option(
        True,
        "--ocr-scanned-pages/--no-ocr-scanned-pages",
        help=(
            "Run OCR for pages marked as scanned-like (low/empty text). "
            "Recommended for mixed PDFs that have a few image-only pages."
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
    workdir_path = _path_arg(workdir)

    info = get_pdf_info(pdf_path)
    text_dir = workdir_path / "text" / info.doc_id

    # 1) render
    is_epub = pdf_path.suffix.lower() == ".epub"
    effective_render = (not is_epub) if render_images is None else render_images
    if effective_render:
        if is_epub:
            typer.echo(
                "EPUB detected: --render-images enabled; rendering may be slow."
            )
        render_pdf_to_images(
            pdf_path,
            workdir_path,
            dpi=dpi,
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
        # Always run OCR for fully scanned docs.
        # Optionally also run OCR for "digital" docs that contain a few
        # scanned-like pages.
        should_ocr = profile.doc_type == DocType.scanned or ocr_scanned_pages
        if should_ocr and effective_render:
            ocr_path = apply_ocr_fallback(
                pdf_path=pdf_path,
                workdir=workdir_path,
                lang=ocr_lang,
            )
            in_path = ocr_path
        elif should_ocr and not effective_render:
            typer.echo(
                "OCR requested, but images were not rendered; skipping OCR. "
                "Enable --render-images to allow OCR."
            )

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
        doc_domain=profile.doc_domain,
    )

    typer.echo(f"doc_id: {info.doc_id}")
    typer.echo(f"profile: type={profile.doc_type}, domain={profile.doc_domain}")
    typer.echo(f"pages_raw: {pages_raw_path}")
    if in_path != pages_raw_path:
        typer.echo(f"pages_with_ocr: {in_path}")
    typer.echo(f"blocks: {blocks_path}")
    typer.echo(f"chunks: {chunks_path}")


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
        doc_domain=effective_domain,
    )
    typer.echo(f"Text-chunks opgeslagen in: {result}")


if __name__ == "__main__":
    app()
