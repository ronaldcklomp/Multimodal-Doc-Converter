from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class DocType(str, Enum):
    """Physical/source type."""

    auto = "auto"
    digital = "digital"
    scanned = "scanned"


class DocDomain(str, Enum):
    """Semantic/document genre."""

    auto = "auto"
    academic = "academic"
    manual = "manual"
    book = "book"


@dataclass
class DocProfile:
    doc_type: DocType
    doc_domain: DocDomain
    scanned_page_ratio: float
    signals: Dict[str, Any]
    decided_by: str = "auto"  # "auto" | "override" | "mixed"
    version: int = 1


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def load_pages_jsonl(jsonl_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def _count_keywords(text: str, keywords: Iterable[str]) -> int:
    t = _normalize_text(text)
    if not t:
        return 0
    score = 0
    for kw in keywords:
        if kw in t:
            score += 1
    return score


def detect_doc_domain(
    sample_text: str,
    *,
    pdf_metadata: Optional[Dict[str, Any]] = None,
) -> tuple[DocDomain, Dict[str, Any]]:
    """Very lightweight heuristic classifier.

    This is intentionally simple (no ML) and should be treated as a prior.
    Users can always override via CLI.
    """

    meta = pdf_metadata or {}
    creator = _normalize_text(str(meta.get("creator", "")))
    producer = _normalize_text(str(meta.get("producer", "")))

    academic_keywords = [
        "abstract",
        "references",
        "bibliography",
        "arxiv",
        "doi",
        "proceedings",
        "thesis",
        "dissertation",
        "methodology",
        "results",
    ]
    manual_keywords = [
        "user guide",
        "manual",
        "installation",
        "safety",
        "warning",
        "caution",
        "troubleshooting",
        "specifications",
        "warranty",
        "faq",
        "quick start",
    ]
    book_keywords = [
        "chapter",
        "table of contents",
        "contents",
        "preface",
        "isbn",
        "copyright",
        "appendix",
        "index",
    ]

    scores = {
        "academic": _count_keywords(sample_text, academic_keywords),
        "manual": _count_keywords(sample_text, manual_keywords),
        "book": _count_keywords(sample_text, book_keywords),
    }

    # Gentle metadata priors
    if "latex" in creator or "pdflatex" in producer or "pdftex" in producer:
        scores["academic"] += 1

    best = max(scores.items(), key=lambda kv: kv[1])
    domain = DocDomain(best[0]) if best[1] > 0 else DocDomain.book
    return domain, {"scores": scores, "creator": creator, "producer": producer}


def detect_doc_profile_from_pages(
    pages: List[Dict[str, Any]],
    *,
    pdf_metadata: Optional[Dict[str, Any]] = None,
    doc_type_override: DocType = DocType.auto,
    doc_domain_override: DocDomain = DocDomain.auto,
) -> DocProfile:
    """Detect doc profile from pages_raw/pages_with_ocr JSONL rows."""

    total = max(1, len(pages))
    scanned_like = sum(1 for r in pages if r.get("is_scanned_like"))
    scanned_ratio = scanned_like / total

    # Type detection: prefer scanned if many pages are scanned-like.
    detected_type = DocType.scanned if scanned_ratio >= 0.3 else DocType.digital

    # Domain detection from first N pages.
    sample_pages = pages[: min(8, len(pages))]
    sample_text = "\n\n".join((r.get("raw_text") or "") for r in sample_pages)
    detected_domain, domain_signals = detect_doc_domain(
        sample_text,
        pdf_metadata=pdf_metadata,
    )

    decided_by = "auto"
    final_type = detected_type
    final_domain = detected_domain

    if doc_type_override != DocType.auto:
        final_type = doc_type_override
        decided_by = "override"
    if doc_domain_override != DocDomain.auto:
        final_domain = doc_domain_override
        decided_by = "override" if decided_by == "auto" else "mixed"

    return DocProfile(
        doc_type=final_type,
        doc_domain=final_domain,
        scanned_page_ratio=float(scanned_ratio),
        signals={
            "scanned_like_pages": scanned_like,
            "total_pages": total,
            **domain_signals,
        },
        decided_by=decided_by,
    )


def doc_meta_path(text_dir: Path) -> Path:
    return text_dir / "doc_meta.json"


def load_doc_profile(text_dir: Path) -> Optional[DocProfile]:
    path = doc_meta_path(text_dir)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    prof = data.get("profile")
    if not prof:
        return None
    return DocProfile(
        doc_type=DocType(prof["doc_type"]),
        doc_domain=DocDomain(prof["doc_domain"]),
        scanned_page_ratio=float(prof.get("scanned_page_ratio", 0.0)),
        signals=dict(prof.get("signals", {})),
        decided_by=str(prof.get("decided_by", "auto")),
        version=int(prof.get("version", 1)),
    )


def save_doc_profile(
    *,
    text_dir: Path,
    doc_id: str,
    source_path: str,
    pdf_metadata: Optional[Dict[str, Any]],
    profile: DocProfile,
) -> Path:
    text_dir.mkdir(parents=True, exist_ok=True)
    path = doc_meta_path(text_dir)
    payload = {
        "doc_id": doc_id,
        "source_path": source_path,
        "pdf_metadata": pdf_metadata or {},
        "profile": asdict(profile),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
