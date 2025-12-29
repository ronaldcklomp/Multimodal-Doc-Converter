"""
State management module for V2.0 Ingestion Engine.

Exports context state classes for hierarchical document tracking.
"""
from .context_state import (
    ContextStateV2,
    create_context_state,
)

__all__ = [
    "ContextStateV2",
    "create_context_state",
]
