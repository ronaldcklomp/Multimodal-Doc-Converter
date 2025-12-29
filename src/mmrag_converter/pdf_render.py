from __future__ import annotations

from dataclasses import dataclass

import fitz  # PyMuPDF
from PIL import Image


@dataclass(frozen=True)
class RenderedPage:
    """In-memory rendered PDF page.

    We keep this in-memory to comply with REQUIREMENTS.md REQ-M1 (no full-page
    PNGs saved to disk).
    """

    image: Image.Image
    zoom: float  # pixels per PDF point (dpi / 72)


def render_page_to_pil(page: fitz.Page, *, dpi: int = 150) -> RenderedPage:
    """Render a PyMuPDF page to a PIL image without writing to disk."""

    zoom = float(dpi) / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    mode = "RGB"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return RenderedPage(image=img, zoom=zoom)


def px_rect_to_pdf_rect(
    *, px0: float, py0: float, px1: float, py1: float, zoom: float
) -> fitz.Rect:
    """Convert a pixel-space rectangle to PDF point-space for fitz clip rects."""

    z = float(zoom) or 1.0
    return fitz.Rect(px0 / z, py0 / z, px1 / z, py1 / z)
