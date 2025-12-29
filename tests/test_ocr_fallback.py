import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz  # PyMuPDF
from PIL import Image, ImageDraw

from mmrag_converter.ocr_engine import apply_ocr_fallback


def _make_single_page_pdf_with_image(pdf_path: Path) -> None:
    """Create a 1-page PDF that contains a raster image.

    We keep the background *not* near-white, so the OCR engine's blank-page
    detector won't classify it as blank.
    """

    img_w, img_h = 1000, 1400
    img = Image.new("RGB", (img_w, img_h), color=(230, 230, 230))
    d = ImageDraw.Draw(img)
    d.text((80, 120), "TEST PAGE", fill=(0, 0, 0))
    d.text((80, 200), "Some content to avoid blank detection.", fill=(0, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    doc = fitz.open()
    try:
        page = doc.new_page(width=img_w, height=img_h)
        rect = fitz.Rect(0, 0, img_w, img_h)
        page.insert_image(rect, stream=png_bytes)
        doc.save(str(pdf_path))
    finally:
        doc.close()


class TestOcrFallback(unittest.TestCase):
    def test_good_ocr_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            workdir = tmp / "workdir"
            pdf_path = tmp / "scan.pdf"
            _make_single_page_pdf_with_image(pdf_path)

            doc_id = pdf_path.stem
            text_dir = workdir / "text" / doc_id
            text_dir.mkdir(parents=True, exist_ok=True)

            # Simulate a scanned-like page: extraction produced almost nothing.
            (text_dir / "pages_raw.jsonl").write_text(
                json.dumps(
                    {
                        "doc_id": doc_id,
                        "page_index": 0,
                        "page_number": 1,
                        "raw_text": "",
                        "is_scanned_like": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            good_text = "This is a test page with enough words to pass the OCR sanity checks."
            with patch(
                "mmrag_converter.ocr_engine.pytesseract.image_to_string",
                return_value=good_text,
            ):
                out_path = apply_ocr_fallback(pdf_path=pdf_path, workdir=workdir, lang="eng")

            rows = [
                json.loads(ln)
                for ln in out_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0].get("from_ocr"))
            self.assertFalse(rows[0].get("is_scanned_like"))
            self.assertFalse(rows[0].get("is_blank_page"))
            self.assertEqual(rows[0].get("raw_text"), good_text.strip())

    def test_garbage_ocr_is_rejected_and_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            workdir = tmp / "workdir"
            pdf_path = tmp / "scan.pdf"
            _make_single_page_pdf_with_image(pdf_path)

            doc_id = pdf_path.stem
            text_dir = workdir / "text" / doc_id
            text_dir.mkdir(parents=True, exist_ok=True)

            original_text = "orig"  # intentionally short (scanned-like)
            (text_dir / "pages_raw.jsonl").write_text(
                json.dumps(
                    {
                        "doc_id": doc_id,
                        "page_index": 0,
                        "page_number": 1,
                        "raw_text": original_text,
                        "is_scanned_like": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            garbage = "!!! ¢¢¢¢¢ ¢¢¢¢¢ ¢¢¢¢¢ !!! ae !!!"
            with patch(
                "mmrag_converter.ocr_engine.pytesseract.image_to_string",
                return_value=garbage,
            ):
                out_path = apply_ocr_fallback(pdf_path=pdf_path, workdir=workdir, lang="eng")

            rows = [
                json.loads(ln)
                for ln in out_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            self.assertEqual(len(rows), 1)

            # Garbage should not be marked as OCR-derived and should not replace
            # the original extracted text.
            self.assertFalse(rows[0].get("from_ocr"))
            self.assertTrue(rows[0].get("is_scanned_like"))
            self.assertEqual(rows[0].get("raw_text"), original_text)
