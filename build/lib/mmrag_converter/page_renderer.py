# src/mmrag_converter/page_renderer.py

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import fitz  # PyMuPDF

from .pdf_loader import get_pdf_info


def render_pdf_to_images(
    pdf_path: Path,
    workdir: Path,
    dpi: int = 200,
) -> List[Tuple[int, Path]]:
    """
    Render elke pagina van een PDF naar PNG.

    Returns:
        List met (page_index (0-based), image_path).
    """
    pdf_path = pdf_path.expanduser().resolve()
    info = get_pdf_info(pdf_path)

    output_dir = workdir / "pages" / info.doc_id
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    try:
        results: List[Tuple[int, Path]] = []
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            # matrix voor DPI
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            filename = f"p{page_index + 1:03d}.png"
            image_path = output_dir / filename
            pix.save(str(image_path))

            results.append((page_index, image_path))
    finally:
        doc.close()

    return results
