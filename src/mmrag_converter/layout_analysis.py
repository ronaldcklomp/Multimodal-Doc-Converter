"""
Layout Analysis Module - V2.0 Compliant
========================================
ENGINE_USE: Docling v2.66.0 (Integrated Layout Analysis)

This module provides layout-aware text extraction using Docling's integrated
layout analysis engine. The bounding box extraction logic (required for
REQ-MM-01 10px padding) is preserved.

REQ Compliance:
- REQ-PDF-01 (De-columnization): Layout engine handles multi-column layouts
- REQ-PDF-02 (Ad Detection): Content classification via layout labels
- REQ-L2: Header/footer suppression via noise label filtering
- REQ-MM-01: Bounding boxes extracted for 10px padding on crops

MIGRATION NOTE: 
- Standalone `surya-ocr` package replaced with Docling's integrated layout
- All bounding box logic PRESERVED for element cropping
- Layout predictor interface maintained for compatibility

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""
from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# ============================================================================
# ENGINE DETECTION
# ============================================================================

# Check for Docling availability (preferred engine)
_DOCLING_AVAILABLE = importlib.util.find_spec("docling") is not None

# Global cache for layout predictor
_LAYOUT_PREDICTOR: Any = None
_DOCLING_CONVERTER: Any = None


# ============================================================================
# DOCLING LAYOUT ENGINE
# ============================================================================

def _get_docling_layout_converter() -> Any:
    """
    Create (and cache) a Docling DocumentConverter configured for layout analysis.
    
    ENGINE_USE: Docling v2.66.0 with integrated layout models
    
    Returns:
        DocumentConverter instance configured for layout extraction
        
    Raises:
        ModuleNotFoundError: If docling is not available
    """
    global _DOCLING_CONVERTER
    if _DOCLING_CONVERTER is not None:
        return _DOCLING_CONVERTER

    if not _DOCLING_AVAILABLE:
        raise ModuleNotFoundError("docling")

    from docling.document_converter import DocumentConverter
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat
    
    # Configure pipeline for layout-aware extraction with bounding boxes
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False  # OCR handled separately per REQ-PDF-03
    pipeline_options.do_table_structure = True
    pipeline_options.generate_page_images = True
    pipeline_options.generate_picture_images = True
    
    _DOCLING_CONVERTER = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
    )
    
    logger.info("ENGINE_USE: Docling v2.66.0 - Layout analysis initialized")
    return _DOCLING_CONVERTER


def _extract_layout_boxes_from_docling(
    pdf_path: Union[str, Path],
    page_number: int,
) -> List[Tuple[float, float, float, float, str, int, float]]:
    """
    Extract layout bounding boxes from Docling's document analysis.
    
    ENGINE_USE: Docling v2.66.0
    
    Returns boxes in format: (x0, y0, x1, y1, label, position, confidence)
    compatible with the original surya_boxes format for REQ-MM-01 padding logic.
    
    Args:
        pdf_path: Path to PDF file
        page_number: 0-indexed page number
        
    Returns:
        List of (x0, y0, x1, y1, label, position, confidence) tuples
    """
    try:
        converter = _get_docling_layout_converter()
        result = converter.convert(str(pdf_path))
        
        layout_boxes: List[Tuple[float, float, float, float, str, int, float]] = []
        position = 0
        
        if hasattr(result, 'document') and result.document:
            doc = result.document
            
            # Iterate through document elements to extract bounding boxes
            for item in doc.iterate_items():
                if hasattr(item, 'prov') and item.prov:
                    for prov in item.prov:
                        # Filter by page number (Docling uses 1-indexed pages)
                        if hasattr(prov, 'page_no') and prov.page_no == page_number + 1:
                            label = str(getattr(item, 'label', 'text'))
                            
                            # Skip noise labels per REQ-L2
                            if _is_noise_label(label):
                                continue
                            
                            # Extract bounding box
                            bbox = getattr(prov, 'bbox', None)
                            if bbox:
                                x0 = float(getattr(bbox, 'l', 0))
                                y0 = float(getattr(bbox, 't', 0))
                                x1 = float(getattr(bbox, 'r', 0))
                                y1 = float(getattr(bbox, 'b', 0))
                                
                                # Skip invalid boxes
                                if x1 > x0 and y1 > y0:
                                    confidence = float(getattr(prov, 'confidence', 1.0))
                                    layout_boxes.append(
                                        (x0, y0, x1, y1, label, position, confidence)
                                    )
                                    position += 1
        
        logger.info(
            f"ENGINE_USE: Docling v2.66.0 - Extracted {len(layout_boxes)} "
            f"layout boxes from page {page_number}"
        )
        return layout_boxes
        
    except Exception as e:
        logger.warning(f"Docling layout extraction failed: {e}")
        return []


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass(frozen=True)
class LayoutElement:
    """
    A minimal layout element used for reading order reconstruction.
    
    REQ-STATE-03: Elements carry spatial metadata for chunk inheritance.
    REQ-MM-01: bbox used for 10px padding calculation on crops.
    """
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points
    label: str
    position: int
    confidence: float = 1.0


# ============================================================================
# NOISE FILTERING (REQ-L2)
# ============================================================================

_NOISE_LABELS = frozenset({
    "pageheader",
    "pagefooter", 
    "page_header",
    "page_footer",
    "footnote",
    "tableofcontents",
    "table_of_contents",
    "header",
    "footer",
    "navigation",
    "advertisement",
})


def _is_noise_label(label: str) -> bool:
    """
    REQ-L2: Suppress common page furniture and non-editorial content.
    REQ-PDF-02: Filter advertisements.
    
    Args:
        label: Element label from layout analysis
        
    Returns:
        True if element should be excluded from text extraction
    """
    return (label or "").lower().replace(" ", "_").replace("-", "_") in _NOISE_LABELS


# ============================================================================
# PYMUPDF TEXT EXTRACTION
# ============================================================================

def _pymupdf_text_blocks(page: fitz.Page) -> List[Tuple[float, float, float, float, str]]:
    """
    Return text blocks from PyMuPDF in page coordinate space.
    
    Used as text data source - layout ordering comes from Docling.
    
    Args:
        page: PyMuPDF page object
        
    Returns:
        List of (x0, y0, x1, y1, text) tuples
    """
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


# ============================================================================
# HEURISTIC DE-COLUMNIZATION FALLBACK (REQ-PDF-01)
# ============================================================================

def _ordered_by_columns(
    *,
    page_width: float,
    items: List[Tuple[float, float, float, float, str]],
) -> List[Tuple[float, float, float, float, str]]:
    """
    Heuristic de-columnization fallback (REQ-PDF-01).
    
    Used when layout engine unavailable or as validation.
    Uses block center for column detection to handle gutter/sidebar cases.
    
    Args:
        page_width: Width of page in PDF points
        items: List of text block tuples
        
    Returns:
        Items reordered by column-aware reading order
    """
    w = float(page_width) or 1.0

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
                if (id(b) not in wide_ids) 
                and (b not in left_bucket) 
                and (b not in right_bucket)
            ],
            key=lambda it: (it[1], it[0]),
        )
        return wide_sorted + left_sorted + right_sorted + middle_sorted

    return sorted(items, key=lambda it: (it[1], it[0]))


# ============================================================================
# MAIN EXTRACTION FUNCTION
# ============================================================================

def extract_layout_aware_text(
    page: fitz.Page,
    *,
    pdf_path: Optional[Union[str, Path]] = None,
    page_number: Optional[int] = None,
    use_docling: bool = True,
) -> str:
    """
    Extract text with layout-aware reading order.
    
    ENGINE_USE: Docling v2.66.0 (Primary) + PyMuPDF Heuristics (Fallback)
    
    REQ Compliance:
    - REQ-PDF-01: De-columnization via layout engine or heuristics
    - REQ-L2: Header/footer suppression via noise filtering
    - REQ-MM-01: Bounding boxes preserved for 10px padding
    
    Args:
        page: PyMuPDF page object
        pdf_path: Path to source PDF (required for Docling analysis)
        page_number: 0-indexed page number (required for Docling analysis)
        use_docling: Whether to attempt Docling analysis first
        
    Returns:
        Extracted text in reading order
    """
    # Defensive: always have a fallback for text extraction
    try:
        raw_blocks = _pymupdf_text_blocks(page)
    except Exception:
        t = page.get_text("text")
        return "" if t is None else str(t)

    if not raw_blocks:
        return ""

    # Docling layout path (preferred when available)
    if use_docling and _DOCLING_AVAILABLE and pdf_path and page_number is not None:
        try:
            # Extract layout boxes using Docling's integrated engine
            layout_boxes = _extract_layout_boxes_from_docling(pdf_path, page_number)
            
            if layout_boxes:
                # Map each PyMuPDF text block to the best overlapping layout box
                # This preserves the original surya_boxes mapping logic for REQ-MM-01
                mapped: List[Tuple[int, float, float, float, float, str, float]] = []
                
                for (x0, y0, x1, y1, text) in raw_blocks:
                    best_pos = 10**9
                    best_area = 0.0
                    best_confidence = 1.0
                    
                    for (bx0, by0, bx1, by1, _label, pos, conf) in layout_boxes:
                        # Calculate intersection area
                        ix0 = max(x0, bx0)
                        iy0 = max(y0, by0)
                        ix1 = min(x1, bx1)
                        iy1 = min(y1, by1)
                        
                        if ix1 > ix0 and iy1 > iy0:
                            inter = (ix1 - ix0) * (iy1 - iy0)
                            if inter > best_area:
                                best_area = inter
                                best_pos = pos
                                best_confidence = conf
                    
                    mapped.append((best_pos, y0, x0, x1, y1, text, best_confidence))

                # Primary sort: layout reading order position; secondary: y/x
                mapped.sort(key=lambda it: (it[0], it[1], it[2]))
                return "\n\n".join(it[5] for it in mapped)
                
        except Exception as e:
            logger.warning(f"Docling layout analysis failed: {e}, using fallback")

    # Fallback to heuristic de-columnization
    logger.info("Using heuristic de-columnization fallback")
    w = float(page.rect.width) or 1.0
    ordered = _ordered_by_columns(page_width=w, items=raw_blocks)
    return "\n\n".join(t for *_, t in ordered)


# ============================================================================
# BOUNDING BOX EXTRACTION FOR ASSET CROPPING (REQ-MM-01)
# ============================================================================

def get_layout_boxes(
    pdf_path: Union[str, Path],
    page_number: int,
) -> List[LayoutElement]:
    """
    Get layout elements with bounding boxes for a specific page.
    
    ENGINE_USE: Docling v2.66.0
    
    CRITICAL: This function provides bounding boxes required for
    REQ-MM-01 (10px padding on visual element crops).
    
    Args:
        pdf_path: Path to PDF file
        page_number: 0-indexed page number
        
    Returns:
        List of LayoutElement objects with bounding boxes
    """
    if not _DOCLING_AVAILABLE:
        logger.warning("Docling not available for layout box extraction")
        return []
    
    boxes = _extract_layout_boxes_from_docling(pdf_path, page_number)
    
    return [
        LayoutElement(
            bbox=(x0, y0, x1, y1),
            label=label,
            position=pos,
            confidence=conf,
        )
        for (x0, y0, x1, y1, label, pos, conf) in boxes
    ]


def get_figure_boxes(
    pdf_path: Union[str, Path],
    page_number: int,
) -> List[LayoutElement]:
    """
    Get bounding boxes for figures/images only.
    
    ENGINE_USE: Docling v2.66.0
    
    CRITICAL: Used for REQ-MM-01 (10px padding) and REQ-MM-02 (naming).
    
    Args:
        pdf_path: Path to PDF file
        page_number: 0-indexed page number
        
    Returns:
        List of LayoutElement objects for figure elements only
    """
    all_boxes = get_layout_boxes(pdf_path, page_number)
    
    figure_labels = {'figure', 'image', 'picture', 'chart', 'diagram', 'photo'}
    
    return [
        elem for elem in all_boxes
        if elem.label.lower() in figure_labels
    ]


def get_table_boxes(
    pdf_path: Union[str, Path],
    page_number: int,
) -> List[LayoutElement]:
    """
    Get bounding boxes for tables only.
    
    ENGINE_USE: Docling v2.66.0
    
    Used for REQ-MM-04 (table structure preservation).
    
    Args:
        pdf_path: Path to PDF file
        page_number: 0-indexed page number
        
    Returns:
        List of LayoutElement objects for table elements only
    """
    all_boxes = get_layout_boxes(pdf_path, page_number)
    
    return [
        elem for elem in all_boxes
        if 'table' in elem.label.lower()
    ]


# ============================================================================
# DOCUMENT STRUCTURE ANALYSIS
# ============================================================================

def analyze_document_structure(
    pdf_path: Union[str, Path],
) -> Dict[str, Any]:
    """
    Analyze full document structure using Docling.
    
    ENGINE_USE: Docling v2.66.0
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Dictionary containing document structure information
    """
    if not _DOCLING_AVAILABLE:
        return {
            "success": False,
            "engine": "docling",
            "error": "Docling not available",
        }
    
    try:
        converter = _get_docling_layout_converter()
        result = converter.convert(str(pdf_path))
        
        structure = {
            "success": True,
            "engine": "docling",
            "version": "2.66.0",
            "pages": [],
            "tables": [],
            "figures": [],
            "headings": [],
        }
        
        if hasattr(result, 'document') and result.document:
            doc = result.document
            
            # Extract structure elements
            for item in doc.iterate_items():
                label = str(getattr(item, 'label', '')).lower()
                text = str(getattr(item, 'text', ''))[:100] if hasattr(item, 'text') else ""
                
                if 'table' in label:
                    structure["tables"].append({"label": label, "preview": text})
                elif label in {'figure', 'image', 'picture'}:
                    structure["figures"].append({"label": label})
                elif 'heading' in label or label.startswith('h'):
                    structure["headings"].append({"label": label, "text": text})
        
        logger.info("ENGINE_USE: Docling v2.66.0 - Document structure analyzed")
        return structure
        
    except Exception as e:
        logger.error(f"Document structure analysis failed: {e}")
        return {
            "success": False,
            "engine": "docling",
            "error": str(e),
        }
