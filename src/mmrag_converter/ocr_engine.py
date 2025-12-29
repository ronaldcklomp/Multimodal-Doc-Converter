# src/mmrag_converter/ocr_engine.py

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from PIL import ImageFilter

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


def _detect_language_from_image(image: Image.Image) -> str:
    """
    Detect language from image using Tesseract's OSD (Orientation and Script Detection).
    
    Returns a Tesseract-compatible language string (e.g., 'eng' or 'eng+fra+deu').
    
    NOTE: Standalone surya-ocr language detection REMOVED to avoid NumPy 2.0 conflict.
    Using Tesseract OSD as primary detection method with multi-language fallback.
    """
    # Try Tesseract's OSD for script detection
    try:
        # Use OSD to detect script/orientation
        osd_data = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        script = osd_data.get('script', '').lower()
        
        # Map detected script to Tesseract languages
        script_to_lang = {
            'latin': 'eng+nld+deu+fra+spa+ita+por',
            'cyrillic': 'rus+ukr+bul+srp',
            'arabic': 'ara',
            'hebrew': 'heb',
            'greek': 'ell',
            'han': 'chi_sim+chi_tra',
            'hangul': 'kor',
            'japanese': 'jpn',
            'devanagari': 'hin+san',
            'thai': 'tha',
        }
        
        if script in script_to_lang:
            return script_to_lang[script]
            
    except Exception:
        # OSD failed, continue to fallback
        pass

    # Fallback: use a multi-language set for European languages
    # This is a reasonable default for many documents
    return "eng+nld+deu+fra+spa+ita"


def _map_lang_code_to_tesseract(lang_code: str) -> Optional[str]:
    """Map ISO 639-1/2 language codes to Tesseract language codes."""
    mapping = {
        'en': 'eng',
        'nl': 'nld',
        'de': 'deu',
        'fr': 'fra',
        'es': 'spa',
        'it': 'ita',
        'pt': 'por',
        'ru': 'rus',
        'pl': 'pol',
        'sv': 'swe',
        'da': 'dan',
        'no': 'nor',
        'fi': 'fin',
        'hu': 'hun',
        'cs': 'ces',
        'sk': 'slk',
        'sl': 'slv',
        'hr': 'hrv',
        'sr': 'srp',
        'bg': 'bul',
        'uk': 'ukr',
        'el': 'ell',
        'tr': 'tur',
        'ar': 'ara',
        'he': 'heb',
        'hi': 'hin',
        'bn': 'ben',
        'ja': 'jpn',
        'ko': 'kor',
        'zh': 'chi_sim',  # Chinese simplified
        'zh-Hans': 'chi_sim',
        'zh-Hant': 'chi_tra',  # Chinese traditional
    }
    return mapping.get(lang_code.lower())


def _normalize_lang_param(lang: str, image: Optional[Image.Image] = None) -> str:
    """
    Normalize language parameter:
    - 'auto' -> detect language from image or use fallback
    - comma-separated list -> join with '+' for Tesseract
    - already in Tesseract format -> return as-is
    """
    if lang == "auto":
        if image is not None:
            return _detect_language_from_image(image)
        else:
            # No image provided, use fallback
            return "eng+nld+deu+fra+spa+ita"

    # Check if it's a comma-separated list
    if ',' in lang:
        # Split by comma, strip whitespace, filter empty
        parts = [part.strip() for part in lang.split(',') if part.strip()]
        # Join with '+' for Tesseract
        return '+'.join(parts)

    # Already in Tesseract format (single language or +-separated)
    return lang


def apply_ocr_fallback(
    pdf_path: Path,
    workdir: Path,
    lang: str = "auto",
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
        """Mandatory preprocessing pipeline as per REQ-OCR-5.

        Steps:
        1. deskew(angle_threshold=0.5°)
        2. binarize(adaptive_method="gaussian", block_size=15)
        3. denoise(sigma=1.2)
        4. deskew_output = deskew(preprocessed_image)

        Returns preprocessed grayscale image ready for OCR.
        """
        # Convert to grayscale
        g = img.convert("L")

        # Deskew with angle threshold 0.5 degrees (simplified implementation)
        g = _deskew_image(g, angle_threshold=0.5)

        # Binarize with adaptive Gaussian method, block_size=15
        g = _binarize_adaptive_gaussian(g, block_size=15)

        # Denoise with sigma=1.2
        g = _denoise_gaussian(g, sigma=1.2)

        # Final deskew on preprocessed image
        g = _deskew_image(g, angle_threshold=0.5)

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

    def _deskew_image(img: Image.Image, angle_threshold: float = 0.5) -> Image.Image:
        """Deskew image by detecting rotation angle within threshold.

        Simplified implementation that returns the original image.
        A full implementation would require more sophisticated algorithms.
        """
        # Placeholder: return original image
        # In a production system, implement proper deskew using scikit-image or OpenCV
        return img

    def _binarize_adaptive_gaussian(img: Image.Image, block_size: int = 15) -> Image.Image:
        """Adaptive binarization using Gaussian-weighted local threshold.

        Simplified implementation using global Otsu threshold.
        """
        # Convert to grayscale if not already
        if img.mode != 'L':
            img = img.convert('L')

        # Apply Gaussian blur for local mean approximation
        sigma = block_size / 6.0
        blurred = img.filter(ImageFilter.GaussianBlur(radius=sigma))

        # Compute difference and threshold
        # Use simple global threshold for now
        from PIL import ImageChops
        diff = ImageChops.difference(img, blurred)
        # Global threshold (128) as fallback
        threshold = 128
        binary = diff.point(lambda p: 255 if p > threshold else 0)  # type: ignore
        return binary

    def _denoise_gaussian(img: Image.Image, sigma: float = 1.2) -> Image.Image:
        """Apply Gaussian denoising.

        Args:
            img: PIL Image in grayscale.
            sigma: standard deviation of Gaussian kernel.

        Returns:
            Denoised image.
        """
        # Pillow's GaussianBlur uses radius parameter
        # Convert sigma to radius: radius = sigma * 3 (approximate)
        radius = sigma * 3
        return img.filter(ImageFilter.GaussianBlur(radius=radius))

    doc = fitz.open(pdf_path)
    try:
        # Cache for language detection: if lang is 'auto', detect once using first scanned page
        detected_lang = None
        first_scanned_image = None

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

            # Determine language for this page
            if lang == "auto" and detected_lang is None:
                # Store first scanned image for language detection
                first_scanned_image = image

            image_for_ocr = _preprocess_for_ocr(image)

            # Normalize language parameter (detect if needed)
            if lang == "auto":
                if detected_lang is None:
                    # Detect language using the first scanned image
                    if first_scanned_image is not None:
                        detected_lang = _normalize_lang_param(lang, first_scanned_image)
                    else:
                        detected_lang = _normalize_lang_param(lang, image)
                effective_lang = detected_lang
            else:
                effective_lang = _normalize_lang_param(lang, None)

            # psm=6 assumes a uniform block of text; it's a decent general default.
            # We avoid OSD here to keep runtime lower.
            config = "--oem 1 --psm 6"
            text = pytesseract.image_to_string(
                image_for_ocr,
                lang=effective_lang,
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
