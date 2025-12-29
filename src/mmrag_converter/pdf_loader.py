# src/mmrag_converter/pdf_loader.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

import fitz  # PyMuPDF

from .epub_loader import read_epub_metadata


@dataclass
class PdfInfo:
    doc_id: str
    path: Path
    num_pages: int
    metadata: Dict[str, Any]


def get_pdf_info(pdf_path: Path) -> PdfInfo:
    """
    Lees basisinformatie over een document.

    Note: despite the name, this function supports PDF and EPUB.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # EPUB: use OPF metadata and the filename stem as doc_id.
    if pdf_path.suffix.lower() == ".epub":
        metadata = read_epub_metadata(pdf_path)
        # We treat spine items as "pages" in the rest of the pipeline.
        # (This is more stable than PyMuPDF's reflowed pagination.)
        try:
            from .epub_loader import load_epub_spine

            _, spine = load_epub_spine(pdf_path)
            num_pages = len(spine)
        except Exception:
            # Fallback: open with PyMuPDF for page count.
            doc = fitz.open(pdf_path)
            try:
                num_pages = doc.page_count
            finally:
                doc.close()

        doc_id = pdf_path.stem
        return PdfInfo(
            doc_id=doc_id,
            path=pdf_path,
            num_pages=num_pages,
            metadata=metadata,
        )

    doc = fitz.open(pdf_path)
    try:
        metadata = doc.metadata or {}
        num_pages = doc.page_count
    finally:
        doc.close()

    doc_id = pdf_path.stem

    return PdfInfo(
        doc_id=doc_id,
        path=pdf_path,
        num_pages=num_pages,
        metadata=metadata,
    )
