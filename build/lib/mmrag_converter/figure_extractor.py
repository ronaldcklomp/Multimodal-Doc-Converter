from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import fitz  # PyMuPDF

from .pdf_loader import get_pdf_info


@dataclass
class FigureAsset:
    doc_id: str
    figure_id: str
    page_index: int
    page_number: int
    # PDF coordinate bbox: x0,y0,x1,y1 (points)
    bbox: List[float]
    area_ratio: float
    image_path: str


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def extract_figures_from_pdf(
    *,
    pdf_path: Path,
    workdir: Path,
    pages_dir: Optional[Path] = None,
    # Note: scientific PDFs often embed figures at ~1-8% of page area.
    min_area_ratio: float = 0.005,
    # Scanned PDFs often have a single full-page raster; avoid exporting that.
    max_area_ratio: float = 0.75,
    # Additional guards against tiny embedded images (logos, separators,
    # glyph fragments).
    min_width_px: int = 140,
    min_height_px: int = 140,
    min_px_area: int = 20_000,
    max_per_page: int = 8,
    dpi: int = 200,
    padding_px: int = 10,
) -> Optional[Path]:
    """Extract likely figure images from a PDF.

    This uses the PDF's image blocks (via `page.get_text("dict")`) to locate
    raster images, and crops them from the rendered page PNGs.

    Notes:
    - Requires rendered page images (`workdir/pages/<doc_id>/pXXX.png`).
    - This is intentionally heuristic and conservative.
    - For fully scanned PDFs, pages often have a single full-page image; we
      avoid extracting those via `max_area_ratio`.

    Returns:
        Path to `figures.jsonl` under `workdir/text/<doc_id>/`, or None when
        page images are missing.
    """

    pdf_path = pdf_path.expanduser().resolve()
    workdir = workdir.expanduser().resolve()
    info = get_pdf_info(pdf_path)
    doc_id = info.doc_id

    text_dir = workdir / "text" / doc_id
    text_dir.mkdir(parents=True, exist_ok=True)
    out_path = text_dir / "figures.jsonl"

    out_rows: List[FigureAsset] = []
    figures_dir: Path | None = None

    doc = fitz.open(pdf_path)
    try:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            page_number = page_index + 1
            # Page dimensions in PDF points.
            pw = float(page.rect.width) or 1.0
            ph = float(page.rect.height) or 1.0
            page_area = pw * ph

            # Parse image blocks.
            try:
                page_dict_raw = page.get_text("dict")
                page_dict: Dict[str, Any] = page_dict_raw if isinstance(page_dict_raw, dict) else {}
            except Exception:
                continue

            blocks: Iterable[Dict[str, Any]] = page_dict.get("blocks") or []
            bboxes: List[Tuple[float, float, float, float, float]] = []
            for b in blocks:
                # type==1 -> image block
                if not isinstance(b, dict) or int(b.get("type", -1)) != 1:
                    continue
                bbox = b.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                x0, y0, x1, y1 = [float(v) for v in bbox]
                # Sanity check
                if x1 <= x0 or y1 <= y0:
                    continue
                area_ratio = ((x1 - x0) * (y1 - y0)) / page_area
                if area_ratio < min_area_ratio or area_ratio > max_area_ratio:
                    continue
                bboxes.append((x0, y0, x1, y1, area_ratio))

            if not bboxes:
                continue

            # Sort by descending area to prefer larger figures.
            bboxes.sort(key=lambda t: t[4], reverse=True)

            # Render-crop directly from the PDF (no full-page PNGs saved).
            zoom = float(dpi) / 72.0
            pad_pts = float(padding_px) / zoom

            # Filter by pixel size at the chosen DPI.
            filtered: List[Tuple[float, float, float, float, float, int, int]] = []
            for (x0, y0, x1, y1, area_ratio) in bboxes:
                # Expand bbox with padding, clamp to page.
                rx0 = _clamp(x0 - pad_pts, 0, pw)
                ry0 = _clamp(y0 - pad_pts, 0, ph)
                rx1 = _clamp(x1 + pad_pts, 0, pw)
                ry1 = _clamp(y1 + pad_pts, 0, ph)
                w_px = int(max(0.0, (rx1 - rx0) * zoom))
                h_px = int(max(0.0, (ry1 - ry0) * zoom))
                if w_px < min_width_px or h_px < min_height_px:
                    continue
                if w_px * h_px < min_px_area:
                    continue
                filtered.append((rx0, ry0, rx1, ry1, area_ratio, w_px, h_px))

            if not filtered:
                continue

            filtered.sort(key=lambda t: t[4], reverse=True)
            filtered = filtered[:max_per_page]

            for idx, (rx0, ry0, rx1, ry1, area_ratio, _w, _h) in enumerate(
                filtered, start=1
            ):
                clip = fitz.Rect(rx0, ry0, rx1, ry1)
                if clip.is_empty:
                    continue

                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
                if pix.width <= 1 or pix.height <= 1:
                    continue

                figure_id = f"{doc_id}_p{page_number:03d}_Figure_{idx:02d}"

                if figures_dir is None:
                    figures_dir = text_dir / "figures"
                    figures_dir.mkdir(parents=True, exist_ok=True)

                out_img = figures_dir / f"{doc_id}_{page_number:03d}_Figure_{idx:02d}.png"
                pix.save(str(out_img))

                out_rows.append(
                    FigureAsset(
                        doc_id=doc_id,
                        figure_id=figure_id,
                        page_index=page_index,
                        page_number=page_number,
                        bbox=[float(rx0), float(ry0), float(rx1), float(ry1)],
                        area_ratio=float(area_ratio),
                        image_path=str(out_img),
                    )
                )
    finally:
        doc.close()

    if not out_rows:
        # Don't create empty artifacts.
        if out_path.exists():
            out_path.unlink()
        return None

    with out_path.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    return out_path
