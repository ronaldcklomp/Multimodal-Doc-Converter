from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class MultimodalChunk:
    doc_id: str
    chunk_id: str
    page_start: int
    page_end: int
    text: str
    tokens_estimate: int
    parent_heading: Optional[str]
    heading_level: Optional[int]
    breadcrumb_path: List[str]
    modality: str
    # page images linked to this chunk (if rendered)
    page_images: List[str]
    # extracted figure images linked to this chunk (if present)
    figures: List[Dict[str, Any]]


def export_multimodal_chunks(
    *,
    chunks_path: Path,
    pages_dir: Path,
    out_path: Path,
) -> Path:
    """Create a multimodal JSONL export.

    Note: Per REQUIREMENTS.md REQ-M1, we do not assume full-page images exist.
    If `pages_dir` doesn't exist, `page_images` will be empty.
    """

    rows: List[Dict[str, Any]] = []
    with chunks_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))

    out: List[MultimodalChunk] = []

    # Optional figures.jsonl support.
    figures_by_page: Dict[int, List[Dict[str, Any]]] = {}
    figures_path = out_path.parent / "figures.jsonl"
    if figures_path.exists():
        with figures_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                pn = int(r.get("page_number", 0) or 0)
                if pn <= 0:
                    continue
                figures_by_page.setdefault(pn, []).append(r)
    for r in rows:
        page_start = int(r["page_start"])
        page_end = int(r["page_end"])
        images: List[str] = []
        if pages_dir.exists():
            for p in range(page_start, page_end + 1):
                img = pages_dir / f"p{p:03d}.png"
                if img.exists():
                    images.append(str(img))

        figs: List[Dict[str, Any]] = []
        if figures_by_page:
            for p in range(page_start, page_end + 1):
                figs.extend(figures_by_page.get(p, []))

        out.append(
            MultimodalChunk(
                doc_id=str(r.get("doc_id", "")),
                chunk_id=str(r.get("chunk_id", "")),
                page_start=page_start,
                page_end=page_end,
                text=str(r.get("text", "")),
                tokens_estimate=int(r.get("tokens_estimate", 0)),
                parent_heading=r.get("parent_heading"),
                heading_level=r.get("heading_level"),
                breadcrumb_path=list(
                    r.get("breadcrumb_path") or r.get("section_path") or []
                ),
                modality=str(r.get("modality") or "text"),
                page_images=images,
                figures=figs,
            )
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for item in out:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    return out_path
