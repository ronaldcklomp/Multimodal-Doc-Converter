from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple
import importlib.util

import fitz  # PyMuPDF


_SURYA_AVAILABLE = importlib.util.find_spec("surya") is not None
_SURYA_PREDICTOR: Any = None


def _get_surya_predictor() -> Any:
    """Create (and cache) a Surya LayoutPredictor if the dependency exists."""

    global _SURYA_PREDICTOR
    if _SURYA_PREDICTOR is not None:
        return _SURYA_PREDICTOR

    if not _SURYA_AVAILABLE:
        raise ModuleNotFoundError("surya")

    from surya.foundation import FoundationPredictor  # type: ignore
    from surya.layout import LayoutPredictor  # type: ignore
    from surya.settings import settings  # type: ignore

    foundation = FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
    _SURYA_PREDICTOR = LayoutPredictor(foundation)
    return _SURYA_PREDICTOR


@dataclass(frozen=True)
class LayoutElement:
    """A minimal layout element used for reading order reconstruction."""

    bbox: Tuple[float, float, float, float]  # x0,y0,x1,y1 in PDF points
    label: str
    position: int


def _pymupdf_text_blocks(page: fitz.Page) -> List[Tuple[float, float, float, float, str]]:
    """Return text blocks from PyMuPDF in page coordinate space."""
    blocks = page.get_text("blocks") or []
    out: List[Tuple[float, float, float, float, str]] = []
    for b in blocks:
        if not b or len(b) < 5:
            continue
        x0, y0, x1, y1, text = b[:5]
        t = ("" if text is None else str(text)).strip()
        if not t:
            continue
        out.append((float(x0), float(y0), float(x1), float(y1), t))
    return out


def _is_noise_label(label: str) -> bool:
    """REQ-L2: suppress common page furniture."""
    lbl = (label or "").lower()
    return lbl in {
        "pageheader",
        "pagefooter",
        "footnote",
        "tableofcontents",
    }


def _ordered_by_columns(
    *,
    page_width: float,
    items: List[Tuple[float, float, float, float, str]],
) -> List[Tuple[float, float, float, float, str]]:
    """Heuristic de-columnization fallback.

    This is similar to the previous implementation, but centralized so Surya
    can plug into the same pipeline.
    """

    w = float(page_width) or 1.0

    # Use the block center instead of x0.
    # Many magazine PDFs have gutters/sidebars that shift x0 such that a strict
    # x0 threshold misclassifies right-column blocks (see PCWorld sample).
    def cx(b: Tuple[float, float, float, float, str]) -> float:
        return (float(b[0]) + float(b[2])) / 2.0

    left_bucket = [b for b in items if cx(b) < w * 0.48]
    right_bucket = [b for b in items if cx(b) > w * 0.52]

    if len(left_bucket) >= 2 and len(right_bucket) >= 2:
        wide = [b for b in items if b[0] < w * 0.20 and b[2] > w * 0.80]
        wide_sorted = sorted(wide, key=lambda it: (it[1], it[0]))
        wide_ids = set(id(b) for b in wide)
        left_sorted = sorted(
            [b for b in left_bucket if id(b) not in wide_ids],
            key=lambda it: (it[1], it[0]),
        )
        right_sorted = sorted(
            [b for b in right_bucket if id(b) not in wide_ids],
            key=lambda it: (it[1], it[0]),
        )
        middle_sorted = sorted(
            [
                b
                for b in items
                if (id(b) not in wide_ids) and (b not in left_bucket) and (b not in right_bucket)
            ],
            key=lambda it: (it[1], it[0]),
        )
        return wide_sorted + left_sorted + right_sorted + middle_sorted

    return sorted(items, key=lambda it: (it[1], it[0]))


def extract_layout_aware_text(
    page: fitz.Page,
    *,
    use_surya: bool = True,
    surya_predictor: Any = None,
) -> str:
    """Extract text attempting to preserve reading order.

    - If Surya is available and enabled: use Surya layout boxes to help order
      text (REQ-L1) and suppress headers/footers (REQ-L2).
    - Otherwise: fall back to a heuristic 2-column ordering.
    """

    # Defensive: always have a fallback.
    try:
        raw_blocks = _pymupdf_text_blocks(page)
    except Exception:
        t = page.get_text("text")
        return "" if t is None else str(t)

    if not raw_blocks:
        return ""

    # Surya path is optional because it brings heavyweight deps (torch).
    if use_surya and _SURYA_AVAILABLE:
        try:
            if surya_predictor is None:
                surya_predictor = _get_surya_predictor()

            # Render a PIL image from the page without saving to disk.
            from .pdf_render import render_page_to_pil

            rendered = render_page_to_pil(page, dpi=200)
            layout_res = surya_predictor([rendered.image])[0]
            boxes = getattr(layout_res, "bboxes", []) or []

            # Convert Surya polygons to simple bboxes in pixel space.
            surya_boxes: List[Tuple[float, float, float, float, str, int]] = []
            for b in boxes:
                label = getattr(b, "label", "")
                if _is_noise_label(label):
                    continue
                poly = getattr(b, "polygon", None)
                if not poly or len(poly) < 4:
                    continue
                xs = [float(p[0]) for p in poly]
                ys = [float(p[1]) for p in poly]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
                surya_boxes.append((x0, y0, x1, y1, str(label), int(getattr(b, "position", 0))))

            if surya_boxes:
                # Map each PyMuPDF text block to the best overlapping Surya box.
                # Surya is in pixel coords of rendered image; map PDF points -> px.
                z = float(rendered.zoom) or 1.0
                mapped: List[Tuple[int, float, float, float, float, str]] = []
                for (x0, y0, x1, y1, t) in raw_blocks:
                    px0, py0, px1, py1 = x0 * z, y0 * z, x1 * z, y1 * z
                    best_pos = 10**9
                    best_area = 0.0
                    for (sx0, sy0, sx1, sy1, _lbl, pos) in surya_boxes:
                        ix0 = max(px0, sx0)
                        iy0 = max(py0, sy0)
                        ix1 = min(px1, sx1)
                        iy1 = min(py1, sy1)
                        if ix1 <= ix0 or iy1 <= iy0:
                            continue
                        inter = (ix1 - ix0) * (iy1 - iy0)
                        if inter > best_area:
                            best_area = inter
                            best_pos = pos
                    mapped.append((best_pos, y0, x0, x1, y1, t))

                # Primary sort: Surya reading order position; secondary: y/x.
                mapped.sort(key=lambda it: (it[0], it[1], it[2]))
                return "\n\n".join(it[-1] for it in mapped)
        except Exception:
            # Hard fallback below.
            pass

    w = float(page.rect.width) or 1.0
    ordered = _ordered_by_columns(page_width=w, items=raw_blocks)
    return "\n\n".join(t for *_, t in ordered)
