from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ContextState:
    """Persistent hierarchy state.

    Matches REQUIREMENTS.md §3.1.

    We intentionally cap hierarchy at 3 levels (h1-h3). Deeper headings are
    treated as h3 for state inheritance.
    """

    current_h1: Optional[str] = None
    current_h2: Optional[str] = None
    current_h3: Optional[str] = None
    breadcrumb_path: List[str] = field(default_factory=list)
    current_page: int = 0

    def set_page(self, page_number: int) -> None:
        self.current_page = int(page_number or 0)

    def ensure_root(self, root: str) -> None:
        """Ensure there's always a non-empty root breadcrumb."""
        if not self.current_h1:
            self.current_h1 = root
        if not self.breadcrumb_path:
            self.breadcrumb_path = [self.current_h1]

    def update_on_heading(self, *, text: str, level: int, page_number: int) -> None:
        """Update the active heading state when a new heading is encountered."""

        self.set_page(page_number)
        t = (text or "").strip()
        if not t:
            return

        lvl = int(level or 1)
        if lvl <= 1:
            self.current_h1 = t
            self.current_h2 = None
            self.current_h3 = None
        elif lvl == 2:
            if self.current_h1 is None:
                # Defensive: maintain a valid breadcrumb even when the first
                # detected heading is level-2.
                self.current_h1 = "Document"
            self.current_h2 = t
            self.current_h3 = None
        else:
            # lvl >= 3
            if self.current_h1 is None:
                self.current_h1 = "Document"
            if self.current_h2 is None:
                self.current_h2 = "Section"
            self.current_h3 = t

        self.breadcrumb_path = [h for h in [self.current_h1, self.current_h2, self.current_h3] if h]

    def to_dict(self) -> dict:
        return {
            "current_h1": self.current_h1,
            "current_h2": self.current_h2,
            "current_h3": self.current_h3,
            "breadcrumb_path": list(self.breadcrumb_path),
            "current_page": int(self.current_page or 0),
        }

