"""
Ingestion JSONL Schema - V2.0 Canonical Output Format
======================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

This module defines the Pydantic schema for the V2.0 compliant ingestion.jsonl
output format. Every line in ingestion.jsonl MUST validate against this schema.

SRS Section 6: CANONICAL OUTPUT SCHEMA (JSONL)
"Every line in `ingestion.jsonl` MUST validate against this schema.
No other output formats are permitted."

Schema Structure (from SRS):
{
  "chunk_id": "UUID_v4",
  "doc_id": "File_Hash_MD5",
  "modality": "text | image | table",
  "content": "The actual text or markdown content.",
  "metadata": {
    "source_file": "manual.pdf",
    "file_type": "pdf",
    "page_number": 42,
    "hierarchy": {
      "parent_heading": "3.2 Installation",
      "breadcrumb_path": ["Chapter 3", "3.2 Installation"],
      "level": 2
    },
    "spatial": {
      "bbox": [100, 200, 500, 600]
    },
    "content_classification": "editorial"
  },
  "asset_ref": {
    "file_path": "assets/manual_p42_fig1.png",
    "visual_description": "Optional AI description"
  },
  "semantic_context": {
    "prev_text_snippet": "As shown in the diagram...",
    "next_text_snippet": "...connect the cable."
  }
}

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# ENUMERATIONS
# ============================================================================

class Modality(str, Enum):
    """
    Content modality types.
    
    SRS: "modality": "text | image | table"
    """
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"


class FileType(str, Enum):
    """
    Supported input file types.
    
    SRS Section 2: Input Format Specifications
    """
    PDF = "pdf"
    EPUB = "epub"
    HTML = "html"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"


class ContentClassification(str, Enum):
    """
    Content classification for filtering.
    
    SRS Section 1.1: Critical Design Mandates - Denoising
    "Non-editorial content (Ads, Navigation, Mastheads) MUST be identified"
    """
    EDITORIAL = "editorial"
    ADVERTISEMENT = "advertisement"
    NAVIGATION = "navigation"
    HEADER = "header"
    FOOTER = "footer"


# ============================================================================
# NESTED SCHEMA MODELS
# ============================================================================

class HierarchyMetadata(BaseModel):
    """
    Hierarchical context from ContextState.
    
    REQ-STATE compliance:
    - parent_heading: Immediate parent section heading
    - breadcrumb_path: Full navigation path ["Chapter 1", "Section 1.2"]
    - level: Heading level (1-6) for depth consistency
    """
    parent_heading: Optional[str] = Field(
        default=None,
        description="The immediate parent heading text"
    )
    breadcrumb_path: List[str] = Field(
        default_factory=list,
        description="Full hierarchical path as list of section headings"
    )
    level: Optional[int] = Field(
        default=None,
        ge=1,
        le=6,
        description="Heading level (1-6) for QA-CHECK-03 validation"
    )
    
    @field_validator("breadcrumb_path")
    @classmethod
    def filter_empty_breadcrumbs(cls, v: List[str]) -> List[str]:
        """Remove empty strings from breadcrumb path."""
        return [b for b in v if b and b.strip()]


class SpatialMetadata(BaseModel):
    """
    Spatial/bounding box information for visual elements.
    
    REQ-MM-01: Bounding boxes for 10px padding on crops
    Format: [x0, y0, x1, y1] in PDF points or pixels
    """
    bbox: Optional[List[float]] = Field(
        default=None,
        min_length=4,
        max_length=4,
        description="Bounding box [x0, y0, x1, y1] in coordinate space"
    )
    
    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        """Validate bounding box has correct format."""
        if v is not None:
            if len(v) != 4:
                raise ValueError("bbox must have exactly 4 values [x0, y0, x1, y1]")
            x0, y0, x1, y1 = v
            if x1 <= x0 or y1 <= y0:
                raise ValueError("Invalid bbox: x1 must be > x0 and y1 must be > y0")
        return v


class ChunkMetadata(BaseModel):
    """
    Complete metadata for a chunk.
    
    Combines source info, hierarchy, spatial data, and classification.
    """
    source_file: str = Field(
        ...,
        description="Original source filename"
    )
    file_type: FileType = Field(
        ...,
        description="Type of source file (pdf, epub, html, etc.)"
    )
    page_number: int = Field(
        ...,
        ge=1,
        description="Page number (1-indexed for display)"
    )
    hierarchy: HierarchyMetadata = Field(
        default_factory=HierarchyMetadata,
        description="Hierarchical context from ContextState"
    )
    spatial: Optional[SpatialMetadata] = Field(
        default=None,
        description="Spatial/bbox data for visual elements"
    )
    content_classification: ContentClassification = Field(
        default=ContentClassification.EDITORIAL,
        description="Classification for content filtering"
    )


class AssetReference(BaseModel):
    """
    Reference to an extracted visual asset.
    
    REQ-MM-02: Naming Standard
    Format: [DocHash]_[PageNum]_[Type]_[Index].png
    Example: a1b2c3d4_005_figure_01.png
    """
    file_path: str = Field(
        ...,
        description="Relative path to the extracted asset file"
    )
    visual_description: Optional[str] = Field(
        default=None,
        description="Optional AI-generated description of the visual"
    )


class SemanticContext(BaseModel):
    """
    Surrounding text context for visual elements.
    
    REQ-MM-03: Contextual Anchoring
    "The JSONL entry for an image MUST contain text_before (300 chars) 
    and text_after (300 chars) from the surrounding text flow."
    """
    prev_text_snippet: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Text before this element (up to 300 chars recommended)"
    )
    next_text_snippet: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Text after this element (up to 300 chars recommended)"
    )


# ============================================================================
# MAIN INGESTION CHUNK SCHEMA
# ============================================================================

class IngestionChunk(BaseModel):
    """
    Complete schema for a single chunk in ingestion.jsonl.
    
    SRS Section 6: CANONICAL OUTPUT SCHEMA (JSONL)
    
    Every line in ingestion.jsonl MUST validate against this schema.
    This is the atomic unit of data for RAG ingestion.
    
    Example:
    ```json
    {
      "chunk_id": "550e8400-e29b-41d4-a716-446655440000",
      "doc_id": "a1b2c3d4e5f6...",
      "modality": "text",
      "content": "Chapter 1: Introduction...",
      "metadata": {
        "source_file": "manual.pdf",
        "file_type": "pdf",
        "page_number": 1,
        "hierarchy": {
          "parent_heading": "Chapter 1",
          "breadcrumb_path": ["Chapter 1"],
          "level": 1
        },
        "content_classification": "editorial"
      }
    }
    ```
    """
    chunk_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier (UUID v4)"
    )
    doc_id: str = Field(
        ...,
        description="Document identifier (MD5 hash of source file)"
    )
    modality: Modality = Field(
        ...,
        description="Content type: text, image, or table"
    )
    content: str = Field(
        ...,
        description="The actual text content or markdown representation"
    )
    metadata: ChunkMetadata = Field(
        ...,
        description="Complete metadata for this chunk"
    )
    asset_ref: Optional[AssetReference] = Field(
        default=None,
        description="Reference to extracted visual asset (for image/table)"
    )
    semantic_context: Optional[SemanticContext] = Field(
        default=None,
        description="Surrounding text context for visual elements"
    )
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "chunk_id": "550e8400-e29b-41d4-a716-446655440000",
                "doc_id": "a1b2c3d4e5f6789012345678901234ab",
                "modality": "text",
                "content": "This is the extracted text content of the chunk.",
                "metadata": {
                    "source_file": "document.pdf",
                    "file_type": "pdf",
                    "page_number": 1,
                    "hierarchy": {
                        "parent_heading": "Introduction",
                        "breadcrumb_path": ["Introduction"],
                        "level": 1
                    },
                    "content_classification": "editorial"
                }
            }
        }


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def create_text_chunk(
    doc_id: str,
    content: str,
    source_file: str,
    file_type: FileType,
    page_number: int,
    hierarchy: Optional[HierarchyMetadata] = None,
    classification: ContentClassification = ContentClassification.EDITORIAL,
) -> IngestionChunk:
    """
    Factory function to create a text chunk.
    
    Args:
        doc_id: MD5 hash of source document
        content: Text content
        source_file: Original filename
        file_type: Type of source file
        page_number: Page number (1-indexed)
        hierarchy: Optional hierarchy metadata
        classification: Content classification
        
    Returns:
        IngestionChunk instance for text content
    """
    return IngestionChunk(
        doc_id=doc_id,
        modality=Modality.TEXT,
        content=content,
        metadata=ChunkMetadata(
            source_file=source_file,
            file_type=file_type,
            page_number=page_number,
            hierarchy=hierarchy or HierarchyMetadata(),
            content_classification=classification,
        ),
    )


def create_image_chunk(
    doc_id: str,
    content: str,
    source_file: str,
    file_type: FileType,
    page_number: int,
    asset_path: str,
    bbox: Optional[List[float]] = None,
    hierarchy: Optional[HierarchyMetadata] = None,
    prev_text: Optional[str] = None,
    next_text: Optional[str] = None,
    visual_description: Optional[str] = None,
) -> IngestionChunk:
    """
    Factory function to create an image/figure chunk.
    
    REQ-MM-01: bbox for 10px padding
    REQ-MM-02: asset_path follows naming convention
    REQ-MM-03: prev_text/next_text for contextual anchoring
    
    Args:
        doc_id: MD5 hash of source document
        content: Description or caption of the image
        source_file: Original filename
        file_type: Type of source file
        page_number: Page number (1-indexed)
        asset_path: Path to extracted asset file
        bbox: Optional bounding box [x0, y0, x1, y1]
        hierarchy: Optional hierarchy metadata
        prev_text: Text before image (REQ-MM-03)
        next_text: Text after image (REQ-MM-03)
        visual_description: Optional AI description
        
    Returns:
        IngestionChunk instance for image content
    """
    spatial = SpatialMetadata(bbox=bbox) if bbox else None
    
    return IngestionChunk(
        doc_id=doc_id,
        modality=Modality.IMAGE,
        content=content,
        metadata=ChunkMetadata(
            source_file=source_file,
            file_type=file_type,
            page_number=page_number,
            hierarchy=hierarchy or HierarchyMetadata(),
            spatial=spatial,
            content_classification=ContentClassification.EDITORIAL,
        ),
        asset_ref=AssetReference(
            file_path=asset_path,
            visual_description=visual_description,
        ),
        semantic_context=SemanticContext(
            prev_text_snippet=prev_text[:300] if prev_text else None,
            next_text_snippet=next_text[:300] if next_text else None,
        ) if (prev_text or next_text) else None,
    )


def create_table_chunk(
    doc_id: str,
    content: str,
    source_file: str,
    file_type: FileType,
    page_number: int,
    bbox: Optional[List[float]] = None,
    hierarchy: Optional[HierarchyMetadata] = None,
    asset_path: Optional[str] = None,
) -> IngestionChunk:
    """
    Factory function to create a table chunk.
    
    REQ-MM-04: Tables converted to Markdown or HTML string representation.
    Tables are NEVER flattened to unstructured text.
    
    Args:
        doc_id: MD5 hash of source document
        content: Markdown or HTML table content
        source_file: Original filename
        file_type: Type of source file
        page_number: Page number (1-indexed)
        bbox: Optional bounding box
        hierarchy: Optional hierarchy metadata
        asset_path: Optional path to table image
        
    Returns:
        IngestionChunk instance for table content
    """
    spatial = SpatialMetadata(bbox=bbox) if bbox else None
    asset_ref = AssetReference(file_path=asset_path) if asset_path else None
    
    return IngestionChunk(
        doc_id=doc_id,
        modality=Modality.TABLE,
        content=content,
        metadata=ChunkMetadata(
            source_file=source_file,
            file_type=file_type,
            page_number=page_number,
            hierarchy=hierarchy or HierarchyMetadata(),
            spatial=spatial,
            content_classification=ContentClassification.EDITORIAL,
        ),
        asset_ref=asset_ref,
    )
