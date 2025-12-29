from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class QualityReport:
    doc_id: str
    source_path: str
    doc_type: str
    doc_domain: str
    total_pages: int

    # OCR
    scanned_like_pages: int
    ocr_pages: int
    ocr_coverage: float

    # Structure
    blocks_total: int
    headings_total: int
    headings_junk: int
    heading_noise_ratio: float

    # Chunks
    chunks_total: int
    chunks_exact_duplicates: int
    chunks_duplicate_ratio: float
    chunks_below_min_tokens: int
    chunks_bad_boundaries: int
    chunks_bad_boundary_ratio: float

    # token stats
    tokens_min: int
    tokens_median: int
    tokens_p95: int
    tokens_max: int


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def _median(values: List[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    return int(s[len(s) // 2])


def _p95(values: List[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = int(len(s) * 0.95)
    idx = min(idx, len(s) - 1)
    return int(s[idx])


def _is_junk_heading(h: str) -> bool:
    s = (h or "").strip()
    if not s:
        return True
    if re.fullmatch(r"SERVES\s+\d+", s, flags=re.I):
        return True
    if re.fullmatch(r"[A-Z]", s):
        return True
    if re.fullmatch(r"[IVXLC]+", s):
        return True
    if re.fullmatch(r"\d{1,4}", s):
        return True
    return False


def evaluate_workdir(
    *,
    doc_id: str,
    source_path: str,
    text_dir: Path,
    min_tokens: int,
) -> QualityReport:
    """Compute quality metrics from produced JSONL artifacts."""

    meta_path = text_dir / "doc_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    profile = meta.get("profile") or {}
    doc_type = (profile.get("doc_type") or "auto")
    doc_domain = (profile.get("doc_domain") or "auto")
    signals = profile.get("signals") or {}
    scanned_like_pages = int(signals.get("scanned_like_pages", 0))
    total_pages = int(signals.get("total_pages", 0))

    # OCR
    ocr_pages = 0
    blank_pages = 0
    ocr_path = text_dir / "pages_with_ocr.jsonl"
    if ocr_path.exists():
        ocr_rows = _load_jsonl(ocr_path)
        ocr_pages = sum(1 for r in ocr_rows if r.get("from_ocr"))
        blank_pages = sum(1 for r in ocr_rows if r.get("is_blank_page"))

    # Exclude blank pages from OCR coverage (they should not be OCR'd).
    effective_scanned = max(0, scanned_like_pages - blank_pages)
    ocr_coverage = (ocr_pages / effective_scanned) if effective_scanned else 1.0

    blocks_path = text_dir / "blocks_structured.jsonl"
    blocks = _load_jsonl(blocks_path)
    headings = [b.get("text", "") for b in blocks if b.get("block_type") == "heading"]
    headings_total = len(headings)
    headings_junk = sum(1 for h in headings if _is_junk_heading(h))
    heading_noise_ratio = (headings_junk / headings_total) if headings_total else 0.0

    chunks_path = text_dir / "chunks_text.jsonl"
    chunks = _load_jsonl(chunks_path)
    chunks_total = len(chunks)
    texts = [c.get("text", "").strip() for c in chunks]
    chunks_exact_duplicates = len(texts) - len(set(texts))
    chunks_duplicate_ratio = (chunks_exact_duplicates / chunks_total) if chunks_total else 0.0
    chunks_below_min_tokens = sum(
        1
        for c in chunks
        if int(c.get("tokens_estimate", 0)) < min_tokens
    )

    token_vals = [int(c.get("tokens_estimate", 0)) for c in chunks]

    # Bad boundary heuristic: chunk-to-chunk break likely occurred mid sentence.
    def _is_bad_boundary(prev_tail: str, next_head: str) -> bool:
        import re

        a = (prev_tail or "").strip()
        b = (next_head or "").strip()
        if not a or not b:
            return False
        if a.endswith("-") and re.match(r"^[a-z]", b):
            return True
        if not re.search(r"[\.\!\?\:]\s*$", a) and re.match(r"^[a-z]", b):
            return True
        if a.endswith(",") and re.match(r"^[a-z]", b):
            return True
        return False

    chunks_bad_boundaries = 0
    for i in range(len(chunks) - 1):
        ta = str(chunks[i].get("text", ""))
        tb = str(chunks[i + 1].get("text", ""))
        tail = " ".join(ta.split())[-120:]
        head = " ".join(tb.split())[:120]
        if _is_bad_boundary(tail, head):
            chunks_bad_boundaries += 1

    chunks_bad_boundary_ratio = (
        chunks_bad_boundaries / max(1, chunks_total)
        if chunks_total
        else 0.0
    )

    return QualityReport(
        doc_id=doc_id,
        source_path=source_path,
        doc_type=str(doc_type),
        doc_domain=str(doc_domain),
        total_pages=total_pages,
        scanned_like_pages=scanned_like_pages,
        ocr_pages=ocr_pages,
        ocr_coverage=float(ocr_coverage),
        blocks_total=len(blocks),
        headings_total=headings_total,
        headings_junk=headings_junk,
        heading_noise_ratio=float(heading_noise_ratio),
        chunks_total=chunks_total,
        chunks_exact_duplicates=chunks_exact_duplicates,
        chunks_duplicate_ratio=float(chunks_duplicate_ratio),
        chunks_below_min_tokens=chunks_below_min_tokens,
        chunks_bad_boundaries=chunks_bad_boundaries,
        chunks_bad_boundary_ratio=float(chunks_bad_boundary_ratio),
        tokens_min=min(token_vals) if token_vals else 0,
        tokens_median=_median(token_vals),
        tokens_p95=_p95(token_vals),
        tokens_max=max(token_vals) if token_vals else 0,
    )


def report_to_json(report: QualityReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2)
