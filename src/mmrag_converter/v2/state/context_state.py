"""
ContextStateV2 - Hierarchical State Machine for V2.0
=====================================================
ENGINE_USE: Claude 4.5 Opus (Architect)

This module implements the V2.0 compliant ContextState with hierarchical
breadcrumb tracking to prevent "Context Bleeding" across document sections.

REQ Compliance:
- REQ-STATE-01: Breadcrumbs UPDATE ONLY when new header explicitly detected
- REQ-STATE-02: New header at Level N replaces existing Level N and removes deeper levels
- REQ-STATE-03: Every chunk MUST inherit a deep copy of current ContextState

SRS Section 3: THE STATE MACHINE
"To prevent 'Context Bleeding' (e.g., Preface getting Chapter 10's title),
the system MUST implement a persistent State Machine."

Author: Claude 4.5 Opus (Architect)
Date: 2025-12-28
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ContextStateV2:
    """
    V2.0 compliant ContextState with hierarchical breadcrumb tracking.
    
    This class maintains the parsing state across document elements to ensure
    proper context inheritance for all generated chunks.
    
    SRS Section 3.1 - The ContextState Object:
    ```python
    class ContextState:
        current_page: int
        breadcrumbs: List[str]  # e.g., ["Chapter 1", "Section 1.2"]
        current_header_level: int
        last_processed_header: str
    ```
    
    Attributes:
        current_page: Current page number (1-indexed for display, 0-indexed internal)
        breadcrumbs: Hierarchical path of section headings
        current_header_level: Level of most recently processed heading (1-6)
        last_processed_header: Text of most recently processed heading
        file_boundary_stack: Stack for EPUB chapter boundaries (REQ-EPUB)
        doc_id: Document identifier (MD5 hash)
        source_file: Original source filename
    """
    current_page: int = 0
    breadcrumbs: List[str] = field(default_factory=list)
    current_header_level: int = 0
    last_processed_header: Optional[str] = None
    file_boundary_stack: List[str] = field(default_factory=list)
    doc_id: Optional[str] = None
    source_file: Optional[str] = None
    
    def update_on_heading(
        self, 
        text: str, 
        level: int, 
        page_number: Optional[int] = None,
    ) -> None:
        """
        Update state when a new heading is detected.
        
        REQ-STATE-01: Breadcrumbs UPDATE ONLY when new header explicitly detected
        REQ-STATE-02: If new header is Level N, replace existing Level N and 
                      remove all deeper levels (N+1, N+2, etc.)
        
        Args:
            text: The heading text
            level: Heading level (1-6, where 1 is highest)
            page_number: Optional page number update
            
        Example:
            state = ContextStateV2()
            state.update_on_heading("Chapter 1", level=1)
            # breadcrumbs = ["Chapter 1"]
            state.update_on_heading("Section 1.1", level=2)
            # breadcrumbs = ["Chapter 1", "Section 1.1"]
            state.update_on_heading("Section 1.2", level=2)
            # breadcrumbs = ["Chapter 1", "Section 1.2"] (1.1 replaced)
            state.update_on_heading("Chapter 2", level=1)
            # breadcrumbs = ["Chapter 2"] (all deeper levels removed)
        """
        if not text or not text.strip():
            return
            
        text = text.strip()
        level = max(1, min(level, 6))  # Clamp to valid range
        
        if page_number is not None:
            self.current_page = page_number
        
        # REQ-STATE-02: Truncate breadcrumbs to level-1, then append new heading
        # Level 1 -> index 0, Level 2 -> index 1, etc.
        target_index = level - 1
        
        if target_index < len(self.breadcrumbs):
            # Replace at this level and remove all deeper
            self.breadcrumbs = self.breadcrumbs[:target_index]
        elif target_index > len(self.breadcrumbs):
            # Fill gaps with empty strings for missing levels
            while len(self.breadcrumbs) < target_index:
                self.breadcrumbs.append("")
        
        self.breadcrumbs.append(text)
        self.current_header_level = level
        self.last_processed_header = text
        
        logger.debug(
            f"ContextState updated: level={level}, header='{text[:30]}...', "
            f"breadcrumbs={self.breadcrumbs}"
        )
    
    def update_page(self, page_number: int) -> None:
        """
        Update current page number.
        
        Args:
            page_number: New page number (0-indexed)
        """
        self.current_page = page_number
    
    def push_file_boundary(self, file_name: str) -> None:
        """
        Push a new file boundary onto the stack (for EPUB chapters).
        
        REQ-EPUB-01: Track internal file boundaries without losing context
        
        Args:
            file_name: Internal filename being entered
        """
        self.file_boundary_stack.append(file_name)
        logger.debug(f"Pushed file boundary: {file_name}")
    
    def pop_file_boundary(self) -> Optional[str]:
        """
        Pop a file boundary from the stack.
        
        Returns:
            The popped filename or None if stack is empty
        """
        if self.file_boundary_stack:
            popped = self.file_boundary_stack.pop()
            logger.debug(f"Popped file boundary: {popped}")
            return popped
        return None
    
    def get_state_copy(self) -> ContextStateV2:
        """
        Return a deep copy of the current state.
        
        REQ-STATE-03: Every generated chunk MUST strictly inherit a deep copy
        of the current ContextState.
        
        Returns:
            Deep copy of this ContextStateV2 instance
        """
        return copy.deepcopy(self)
    
    def get_parent_heading(self) -> Optional[str]:
        """
        Get the immediate parent heading from breadcrumbs.
        
        Returns:
            Parent heading text or None if no breadcrumbs
        """
        if self.breadcrumbs:
            return self.breadcrumbs[-1]
        return None
    
    def get_breadcrumb_path(self) -> List[str]:
        """
        Get breadcrumb path with consecutive duplicates removed.
        
        FIX: Remove consecutive duplicate breadcrumbs only.
        Example: ["INTERNET", "INTERNET", "Security"] -> ["INTERNET", "Security"]
        
        Returns:
            List of non-empty breadcrumb strings (consecutive dups removed)
        """
        # Filter empty strings first
        filtered = [b for b in self.breadcrumbs if b]
        # Remove consecutive duplicates
        return [x for i, x in enumerate(filtered) if i == 0 or x != filtered[i-1]]
    
    def get_breadcrumb_depth(self) -> int:
        """
        Get the depth of the current breadcrumb path.
        
        Used for QA-CHECK-03: Verify breadcrumb_path depth consistency.
        
        Returns:
            Number of non-empty breadcrumbs
        """
        return len(self.get_breadcrumb_path())
    
    def to_metadata_dict(self) -> Dict[str, Any]:
        """
        Convert state to metadata dictionary for chunk embedding.
        
        Returns:
            Dictionary matching the hierarchy section of ingestion.jsonl schema
        """
        return {
            "parent_heading": self.get_parent_heading(),
            "breadcrumb_path": self.get_breadcrumb_path(),
            "level": self.current_header_level if self.current_header_level > 0 else None,
        }
    
    def reset(self) -> None:
        """
        Reset state for a new document.
        """
        self.current_page = 0
        self.breadcrumbs = []
        self.current_header_level = 0
        self.last_processed_header = None
        self.file_boundary_stack = []
        logger.debug("ContextState reset")
    
    def __repr__(self) -> str:
        return (
            f"ContextStateV2(page={self.current_page}, "
            f"breadcrumbs={self.breadcrumbs}, "
            f"level={self.current_header_level})"
        )


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_context_state(
    doc_id: Optional[str] = None,
    source_file: Optional[str] = None,
) -> ContextStateV2:
    """
    Factory function to create a new ContextStateV2 instance.
    
    Args:
        doc_id: Document identifier (MD5 hash)
        source_file: Original source filename
        
    Returns:
        New ContextStateV2 instance
    """
    return ContextStateV2(
        doc_id=doc_id,
        source_file=source_file,
    )
