# src/mmrag_converter/ocr_engine.py

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

import pytesseract
from PIL import Image

from .pdf_loader import get_pdf_info


@dataclass
class RawPageText:
    doc_id: str
    page_index: int      # 0-based
    page_number: int     # 1-based
    raw_text: str
    is_scanned_like: bool
    from_ocr: bool = False


def _load_raw_pages(jsonl_path: Path) -> List[RawPageText]:
    rows: List[RawPageText] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            rows.append(
                RawPageText(
                    doc_id=data["doc_id"],
                    page_index=data["page_index"],
                    page_number=data["page_number"],
                    raw_text=data.get("raw_text", ""),
                    is_scanned_like=data.get("is_scanned_like", False),
                    from_ocr=data.get("from_ocr", False),
                )
            )
    return rows


def _save_raw_pages(rows: List[RawPageText], jsonl_path: Path) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")


def apply_ocr_fallback(
    pdf_path: Path,
    workdir: Path,
    lang: str = "eng",
) -> Path:
    """
    Vervang lege/gescande pagina's in pages_raw.jsonl door OCR-tekst
    op basis van de gerenderde pagina-afbeeldingen.
    """
    pdf_path = pdf_path.expanduser().resolve()
    info = get_pdf_info(pdf_path)

    text_dir = workdir / "text" / info.doc_id
    in_path = text_dir / "pages_raw.jsonl"
    if not in_path.exists():
        raise FileNotFoundError(f"Raw text JSONL not found: {in_path}")

    pages_dir = workdir / "pages" / info.doc_id
    if not pages_dir.exists():
        raise FileNotFoundError(f"Pages image dir not found: {pages_dir}")

    rows = _load_raw_pages(in_path)

    for row in rows:
        if not row.is_scanned_like:
            continue

        img_name = f"p{row.page_number:03d}.png"
        img_path = pages_dir / img_name
        if not img_path.exists():
            # Geen image -> sla OCR over, maar laat flag staan
            continue

        image = Image.open(img_path)
        text = pytesseract.image_to_string(image, lang=lang).strip()

        if text:
            row.raw_text = text
            row.is_scanned_like = False
            row.from_ocr = True

    out_path = text_dir / "pages_with_ocr.jsonl"
    _save_raw_pages(rows, out_path)
    return out_path
