# src/mmrag_converter/text_extractor.py

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

import fitz  # PyMuPDF

from .pdf_loader import get_pdf_info
from .epub_loader import extract_epub_text_by_spine
from .layout_analysis import extract_layout_aware_text


@dataclass
class RawPageText:
    doc_id: str
    page_index: int          # 0-based
    page_number: int         # 1-based
    raw_text: str
    is_scanned_like: bool    # True als er vrijwel geen digitale tekst is


def extract_text_per_page(
    pdf_path: Path,
    workdir: Path,
    min_chars_for_digital: int = 30,
) -> Path:
    """
    Extraheer ruwe tekst per pagina en sla op als JSON-lines bestand.

    Returns:
        Path naar het JSONL-bestand met RawPageText records.
    """
    pdf_path = pdf_path.expanduser().resolve()
    info = get_pdf_info(pdf_path)

    output_dir = workdir / "text" / info.doc_id
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "pages_raw.jsonl"

    rows: List[RawPageText] = []

    # EPUB: extract by spine order (XHTML) to avoid reflowed pagination.
    if pdf_path.suffix.lower() == ".epub":
        texts = extract_epub_text_by_spine(pdf_path)
        for page_index, raw in enumerate(texts):
            text_stripped = (raw or "").strip()
            # EPUB is always "digital" text.
            is_scanned = False
            rows.append(
                RawPageText(
                    doc_id=info.doc_id,
                    page_index=page_index,
                    page_number=page_index + 1,
                    raw_text=text_stripped,
                    is_scanned_like=is_scanned,
                )
            )
    else:
        doc = fitz.open(pdf_path)
        try:
            for page_index in range(doc.page_count):
                page = doc.load_page(page_index)
                # Layout-aware ordering with optional Surya integration.
                raw_text = extract_layout_aware_text(page)
                text_stripped = (raw_text or "").strip()

                is_scanned = len(text_stripped) < min_chars_for_digital

                row = RawPageText(
                    doc_id=info.doc_id,
                    page_index=page_index,
                    page_number=page_index + 1,
                    raw_text=text_stripped,
                    is_scanned_like=is_scanned,
                )
                rows.append(row)
        finally:
            doc.close()

    # Schrijf als JSONL zodat latere stappen makkelijk per regel kunnen
    # streamen
    with output_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")

    return output_path
