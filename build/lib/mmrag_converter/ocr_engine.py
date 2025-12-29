# src/mmrag_converter/ocr_engine.py

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from PIL import ImageFilter, ImageOps

from .pdf_loader import get_pdf_info


@dataclass
class RawPageText:
    doc_id: str
    page_index: int      # 0-based
    page_number: int     # 1-based
    raw_text: str
    is_scanned_like: bool
    from_ocr: bool = False
    is_blank_page: bool = False


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
                    is_blank_page=data.get("is_blank_page", False),
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
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(
            f"OCR fallback is PDF-only by default. Got: {pdf_path.suffix} ({pdf_path})"
        )
    info = get_pdf_info(pdf_path)

    text_dir = workdir / "text" / info.doc_id
    in_path = text_dir / "pages_raw.jsonl"
    if not in_path.exists():
        raise FileNotFoundError(f"Raw text JSONL not found: {in_path}")

    rows = _load_raw_pages(in_path)

    def _ocr_text_looks_sane(text: str) -> bool:
        """Reject obvious garbage OCR.

        The goal is *not* to perfectly judge OCR quality; it's to avoid
        overwriting existing extracted text with clearly nonsensical output.

        Heuristics are intentionally lightweight:
        - Require enough characters.
        - Require enough alphanumerics and not too many symbols.
        - Require that letter-containing tokens look like words (not mostly
          1-2 character fragments).
        """

        t = (text or "").strip()
        # Allow short but meaningful OCR (covers/titles). We still reject
        # extremely short outputs which are typically page numbers or noise.
        if len(t) < 10:
            return False

        non_ws = [c for c in t if not c.isspace()]
        if not non_ws:
            return False

        alnum = sum(1 for c in non_ws if c.isalnum())
        alpha = sum(1 for c in non_ws if c.isalpha())
        digit = sum(1 for c in non_ws if c.isdigit())
        other = len(non_ws) - alnum

        alnum_ratio = alnum / max(1, len(non_ws))
        alpha_ratio = alpha / max(1, len(non_ws))
        digit_ratio = digit / max(1, len(non_ws))
        other_ratio = other / max(1, len(non_ws))

        # Too many symbols/punctuation compared to letters/digits.
        if alnum_ratio < 0.55:
            return False
        if other_ratio > 0.35:
            return False

        # Must have a reasonable amount of letters, unless it's clearly a
        # numeric-heavy page (tables, forms, etc.).
        if alpha_ratio < 0.18 and digit_ratio < 0.30:
            return False

        # Token quality: if we have words, they shouldn't be mostly 1-2 char
        # fragments (common garbage OCR pattern).
        raw_tokens = [tok for tok in re.split(r"\s+", t) if tok]

        # strip leading/trailing punctuation/symbols but keep internal hyphens.
        strip_chars = "\"'`.,;:!?()[]{}<>|\\/+=*_~"
        letter_tokens: list[str] = []
        for tok in raw_tokens:
            st = tok.strip(strip_chars)
            if any(ch.isalpha() for ch in st):
                letter_tokens.append(st)

        if letter_tokens:
            avg_len = sum(len(tok) for tok in letter_tokens) / max(1, len(letter_tokens))
            long_ratio = sum(1 for tok in letter_tokens if len(tok) >= 4) / max(
                1, len(letter_tokens)
            )
            # Stronger guard for short OCR outputs: if it's mostly fragments,
            # it's likely garbage.
            if len(t) < 25:
                if avg_len < 3.2 and long_ratio < 0.25:
                    return False
            else:
                if avg_len < 3.0 and long_ratio < 0.20:
                    return False

        # Reject if there are a lot of weird unicode symbols (currency/math/etc)
        # relative to the text size.
        weird = 0
        for c in non_ws:
            cat = unicodedata.category(c)
            if cat and cat[0] in {"C", "S"}:  # control or symbol
                weird += 1
        if (weird / max(1, len(non_ws))) > 0.08:
            return False

        return True

    def _image_is_blank(img: Image.Image) -> bool:
        """Detect completely blank/solid pages.

        This prevents penalizing OCR coverage on separator/blank pages.
        """
        g = img.convert("L")
        hist = g.histogram()
        total = sum(hist) or 1
        mean = sum(i * hist[i] for i in range(256)) / total
        var = sum(((i - mean) ** 2) * hist[i] for i in range(256)) / total
        std = var**0.5
        near_white = sum(hist[246:]) / total
        near_black = sum(hist[:10]) / total

        # Very white (typical blank PDF pages)
        if near_white >= 0.995 and std < 2.0:
            return True
        # Very dark solid pages (separators)
        if near_black >= 0.995 and std < 2.0:
            return True
        # Almost-uniform dark gray (common in some scans)
        if std < 6.0 and mean < 45.0:
            return True

        return False

    def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
        """Lightweight preprocessing to improve OCR across diverse scans."""
        g = img.convert("L")
        g = ImageOps.autocontrast(g)

        # Upscale tiny pages (improves OCR for covers/low-res scans).
        w, h = g.size
        if w < 900:
            scale = 2
            if w < 450:
                scale = 4
            g = g.resize((w * scale, h * scale), resample=Image.Resampling.LANCZOS)

        # Mild sharpening helps low-contrast scans.
        g = g.filter(ImageFilter.SHARPEN)
        return g

    doc = fitz.open(pdf_path)
    try:
        for row in rows:
            if not row.is_scanned_like:
                continue

            # Render in-memory to comply with REQUIREMENTS.md REQ-M1.
            page = doc.load_page(int(row.page_index))
            zoom = 200 / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            if _image_is_blank(image):
                row.raw_text = ""
                row.is_scanned_like = False
                row.from_ocr = False
                row.is_blank_page = True
                continue

            image_for_ocr = _preprocess_for_ocr(image)

            # psm=6 assumes a uniform block of text; it's a decent general default.
            # We avoid OSD here to keep runtime lower.
            config = "--oem 1 --psm 6"
            text = pytesseract.image_to_string(
                image_for_ocr,
                lang=lang,
                config=config,
            ).strip()

            if text and _ocr_text_looks_sane(text):
                row.raw_text = text
                row.is_scanned_like = False
                row.from_ocr = True
                row.is_blank_page = False
            else:
                # Keep the original extracted text. We do *not* mark the page
                # as OCR-derived if the output is empty or looks like garbage.
                row.from_ocr = False
                row.is_blank_page = False
    finally:
        doc.close()

    out_path = text_dir / "pages_with_ocr.jsonl"
    _save_raw_pages(rows, out_path)
    return out_path
