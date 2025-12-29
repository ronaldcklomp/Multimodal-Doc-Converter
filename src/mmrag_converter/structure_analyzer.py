from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .doc_profile import DocDomain
from .state_machine import ContextState


KNOWN_SINGLE_WORD_HEADINGS = {
    "abstract",
    "sammanfattning",
    "acronyms",
    "abbreviations",
    "contents",
    "list of figures",
    "list of tables",
    "acknowledgments",
    "acknowledgements",
    "introduction",
    "discussion",
    "conclusions",
    "references",
}


@dataclass
class Block:
    doc_id: str
    page_index: int
    page_number: int
    block_id: str
    block_type: str          # "heading" | "paragraph"
    heading_level: int | None
    text: str
    parent_heading: str | None
    # Per REQUIREMENTS.md §3.1
    breadcrumb_path: List[str]
    # Per v1.3.1: confidence from structure analysis model
    heading_confidence: float = 1.0
    # Per v1.3.1: physical context for rootless blocks
    physical_context: Dict[str, Any] | None = None
    # Per v1.3.1: format-specific block metadata
    format_specific: Dict[str, Any] | None = None


def _insert_spaces_camel_case(text: str) -> str:
    """
    Voeg spaties toe tussen CamelCase-delen.
    Voorbeeld: 'SchematicNetworkExtraction' -> 'Schematic Network Extraction'
    """
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    return text


def _looks_like_numbered_heading(line: str) -> Tuple[bool, int]:
    """
    Herken patronen als '3', '3.2', '2.1.4 Titel...'
    Return (is_heading, level).
    """
    # Only treat as a numbered heading if the remainder contains
    # alphabetic characters. This prevents false positives on lines like
    # "0 1 1 0 0 0" (tables/matrices/figures).
    # Section numbering in real documents almost never starts with 0.*.
    match = re.match(r"^([1-9]\d*(?:\.\d+)*)\s+(.+)$", line)
    if not match:
        return False, 0
    number_str = match.group(1)
    # Avoid colophon/address lines like "16341 Panketal".
    # Treat large plain integers without dots as non-headings.
    if "." not in number_str:
        try:
            if int(number_str) >= 100:
                return False, 0
        except ValueError:
            return False, 0
    remainder = match.group(2)
    if not re.search(r"[A-Za-z]", remainder):
        return False, 0
    # Headings typically start with a capital letter (or parentheses).
    rem = remainder.strip()
    if not re.match(r"^[A-Z(\[]", rem):
        return False, 0
    parts = match.group(1).split(".")
    return True, len(parts)


def _looks_like_caps_heading(line: str) -> bool:
    """
    Simpele heuristiek: veel hoofdletters, weinig punten.
    """
    if len(line) > 80:
        return False
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return False
    # Avoid single-letter "headings" like "X" / "H".
    if len(letters) < 4:
        return False
    upper_ratio = sum(c.isupper() for c in letters) / len(letters)
    return upper_ratio > 0.7


def _looks_like_equation_or_noise(line: str) -> bool:
    """Heuristics to prevent math fragments and noise from becoming headings."""

    s = line.strip()
    if not s:
        return True
    if len(s) <= 2:
        return True

    # Many PDFs yield single-letter or symbol fragments on figure/math pages.
    alpha = sum(ch.isalpha() for ch in s)
    if alpha == 0:
        return True

    non_alpha = len(s) - alpha
    if non_alpha / max(1, len(s)) > 0.5:
        return True

    # Contains typical math symbols/operators.
    if re.search(r"[=<>±×÷∑∫√≈≠≤≥→↔∥•]", s):
        return True

    # Looks like a matrix row / numeric sequence.
    if re.fullmatch(r"[0-9\s.,:+\-*/()]+", s) and len(s.split()) >= 4:
        return True

    return False


def _looks_like_title_case_heading(line: str) -> bool:
    """
    Titel-case heading: enkele woorden, elk begint met hoofdletter.
    Na CamelCase-fix werkt dit ook voor bijv. 'Schematic Network Extraction'.
    """
    words = line.split()
    if not 1 < len(words) <= 10:
        return False
    for word in words:
        if not word[0].isupper():
            return False
    return True


def _looks_like_chapter_title_candidate(line: str) -> bool:
    """Heuristic for a short book/epub chapter title line."""
    s = line.strip()
    if not s:
        return False
    if not re.search(r"[A-Za-z]", s):
        return False
    if len(s) > 80:
        return False
    if s.endswith((",", ";", ":")):
        return False
    words = s.split()
    if not (2 <= len(words) <= 12):
        return False
    if _looks_like_title_case_heading(s):
        return True
    # Allow short all-caps titles like "WHY WE AGE".
    if _looks_like_caps_heading(s) and len(words) <= 6:
        return True
    return False


def _looks_like_person_name(line: str) -> bool:
    """
    Herken simpele persoonsnamen, bv. 'Lisa Olofsson'.
    Alleen eerste 2–3 pagina's gebruiken we dit om headings te onderdrukken.
    """
    words = line.split()
    if not (2 <= len(words) <= 3):
        return False
    cleaned = [re.sub(r"[.,]$", "", w) for w in words]
    if any(any(ch.isdigit() for ch in w) for w in cleaned):
        return False
    if not all(w and w[0].isupper() for w in cleaned):
        return False
    return True


def _looks_like_affiliation(line: str) -> bool:
    """
    Herken affiliaties zoals 'Umeå University', 'Department of Physics', etc.
    """
    lower = line.lower()
    for kw in ("university", "department", "faculty", "institute"):
        if kw in lower:
            return True
    for kw in ("company", "corp", "ltd", "llc", "gmbh", "inc"):
        if kw in lower:
            return True
    return False


def _looks_like_name_with_affiliation(line: str) -> bool:
    """E.g. "Daniel Egelrud, Combitech AB".

    These are common on title pages and should not become headings.
    """
    if "," not in line:
        return False
    left, right = [s.strip() for s in line.split(",", 1)]
    if not left or not right:
        return False

    # left side: likely a name
    if not _looks_like_person_name(left):
        return False

    # right side: likely an org
    lower_right = right.lower()
    if any(
        kw in lower_right
        for kw in (
            "university",
            "department",
            "institute",
            "ab",
            "ltd",
            "llc",
            "gmbh",
            "inc",
            "corp",
        )
    ):
        return True
    return False


def _looks_like_glossary_entry(line: str) -> bool:
    """Detect acronym/glossary entries like: "AI Artificial Intelligence"."""

    s = line.strip()
    # common pattern: 2-6 uppercase letters, then 2+ title-case words
    if re.fullmatch(r"[A-Z]{2,6}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", s):
        return True
    # allow the acronym to include digits or dashes (e.g., "I2C")
    if re.fullmatch(r"[A-Z0-9\-]{2,8}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", s):
        return True
    return False


def _looks_like_academic_figure_label(line: str) -> bool:
    """Detect short labels typically extracted from figures/axes.

    Examples: "GT Nets", "RAG Predictions".

    These are often not true section headings.
    """
    s = line.strip()

    # 1) Abbreviation + titlecase word (e.g. "GT Nets")
    if re.fullmatch(r"[A-Z]{2,6}\s+[A-Z][a-z]{2,}\b", s):
        return True

    # 2) Common axis labels are short title-cased phrases ending with certain
    # nouns.
    if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}", s):
        last = s.split()[-1]
        if last in {"Nets", "Predictions", "Prefix", "Value", "Values"}:
            return True

    return False


def _detect_heading(line: str, *, doc_domain: DocDomain) -> Tuple[bool, int]:
    """
    Bepaal of een regel een heading lijkt.
    """
    # Book-specific noise filters.
    if doc_domain == DocDomain.book:
        if re.fullmatch(r"SERVES\s+\d+", line.strip(), flags=re.I):
            return False, 0
        # A lot of PDFs contain stray single-letter headings from layout.
        if re.fullmatch(r"[A-Z]", line.strip()):
            return False, 0
        if re.fullmatch(r"[IVXLC]+", line.strip()):
            return False, 0
        # Suppress long OCR-style ALL CAPS lines on title pages.
        if _looks_like_caps_heading(line):
            w = line.strip().split()
            if len(line.strip()) > 40 or len(w) > 6:
                return False, 0

    # Eerst: bekende één-woord headings zoals 'Abstract', 'Contents', etc.
    norm = re.sub(r"[^A-Za-z0-9]+", " ", line).strip().lower()
    if norm in KNOWN_SINGLE_WORD_HEADINGS:
        return True, 1

    if doc_domain == DocDomain.academic and _looks_like_equation_or_noise(line):
        return False, 0

    if doc_domain == DocDomain.academic and _looks_like_glossary_entry(line):
        return False, 0

    if (
        doc_domain == DocDomain.academic
        and _looks_like_academic_figure_label(line)
    ):
        return False, 0

    # Appendix-style headings: "A.1", "B.5".
    # Avoid treating bare single letters as headings across domains.
    # Single-letter fragments are very common in magazines/manuals.
    if doc_domain != DocDomain.book and re.fullmatch(r"[A-Z]\.\d+(?:\.\d+)*", line.strip()):
        level = 1 + line.count(".")
        return True, level

    # Chapter headings in multiple languages (common in EPUB/books).
    # Examples: "Hoofdstuk 1: ...", "Chapter 2 - ...", "Kapitel 3 ..."
    if re.match(
        r"^(hoofdstuk|chapter|kapitel)\s+\d+\b",
        line.strip(),
        flags=re.I,
    ):
        return True, 1

    numbered, level = _looks_like_numbered_heading(line)
    if numbered:
        return True, level
    if _looks_like_caps_heading(line):
        return True, 1
    if _looks_like_title_case_heading(line):
        return True, 1
    return False, 0


def analyze_text_structure(
    *,
    in_path: Path,
    out_path: Path,
    doc_domain: DocDomain = DocDomain.book,
) -> Path:
    """
    Lees pages_raw/pages_with_ocr JSONL en produceer blokken
    (headings + paragrafen) in JSONL-vorm.
    """
    rows: List[Dict[str, Any]] = []
    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))

    rows.sort(key=lambda r: (r["doc_id"], r["page_number"]))

    def _normalize_running_line(raw_line: str) -> str:
        """Normalize a raw line for header/footer suppression.

        Must match the transformations performed in the main parsing loop.
        """
        s = (raw_line or "").strip()
        if not s:
            return ""
        s = _insert_spaces_camel_case(s)

        # Normalize common book patterns (doesn't hurt other domains).
        m = re.match(r"^(CHAPTER\s+\d+)\s+(.+)$", s, flags=re.I)
        if m:
            s = f"{m.group(1).upper()} — {m.group(2).strip()}"
        m = re.match(r"^(PART\s+[IVXLC]+)\s+(.+)$", s, flags=re.I)
        if m:
            s = f"{m.group(1).upper()} — {m.group(2).strip()}"

        # Drop pure page numbers.
        if re.fullmatch(r"\d{1,4}", s):
            return ""

        # Normalize common running footer/header patterns by removing
        # standalone numbers (page numbers) and collapsing whitespace.
        # Example: "8 PC World JULY 2025" -> "PC World JULY 2025".
        s = re.sub(r"\b\d{1,4}\b", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _compute_running_header_footer_suppression(
        rows_for_doc: List[Dict[str, Any]],
        *,
        doc_domain: DocDomain,
    ) -> Dict[int, set[str]]:
        """Return {page_number -> set(lines_to_skip)} for likely running headers/footers.

        This is intentionally conservative and only runs for non-book domains.
        """

        if doc_domain == DocDomain.book:
            return {}

        total_pages = max(1, len(rows_for_doc))
        # Require the line to appear on >=20% of pages AND at least 6 pages.
        min_pages = max(6, int(total_pages * 0.20))

        top_counts: Counter[str] = Counter()
        bottom_counts: Counter[str] = Counter()

        per_page_top: Dict[int, List[str]] = {}
        per_page_bottom: Dict[int, List[str]] = {}

        for r in rows_for_doc:
            page_number = int(r.get("page_number", 0) or 0)
            if page_number <= 1:
                # Never suppress the title page.
                continue
            raw_text = (r.get("raw_text") or "")
            raw_lines = raw_text.splitlines()
            lines = [
                _normalize_running_line(ln)
                for ln in raw_lines
                if _normalize_running_line(ln)
            ]
            if not lines:
                continue

            top = lines[:2]
            bottom = lines[-2:]

            per_page_top[page_number] = top
            per_page_bottom[page_number] = bottom

            # Count at most once per page per line.
            for ln in set(top):
                top_counts[ln] += 1
            for ln in set(bottom):
                bottom_counts[ln] += 1

        def _header_like(line: str) -> bool:
            s = (line or "").strip()
            if not s:
                return False
            if len(s) < 4 or len(s) > 80:
                return False
            if not re.search(r"[A-Za-z]", s):
                return False
            # Avoid suppressing very long, content-heavy lines.
            if len(s.split()) > 12:
                return False
            return _looks_like_caps_heading(s) or _looks_like_title_case_heading(s)

        suppress_global: set[str] = set()
        for line, c in top_counts.items():
            if c >= min_pages and _header_like(line):
                suppress_global.add(line)
        for line, c in bottom_counts.items():
            if c >= min_pages and _header_like(line):
                suppress_global.add(line)

        suppress_by_page: Dict[int, set[str]] = defaultdict(set)
        if not suppress_global:
            return {}

        for page_number, top in per_page_top.items():
            for ln in top:
                if ln in suppress_global:
                    suppress_by_page[page_number].add(ln)
        for page_number, bottom in per_page_bottom.items():
            for ln in bottom:
                if ln in suppress_global:
                    suppress_by_page[page_number].add(ln)

        return dict(suppress_by_page)

    # Compute per-doc header/footer suppression sets (page_number -> lines).
    rows_by_doc: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        rows_by_doc[str(r.get("doc_id", ""))].append(r)
    for doc_rows in rows_by_doc.values():
        doc_rows.sort(key=lambda r: int(r.get("page_number", 0) or 0))

    suppress_lines: Dict[Tuple[str, int], set[str]] = {}
    for doc_id_key, doc_rows in rows_by_doc.items():
        by_page = _compute_running_header_footer_suppression(
            doc_rows,
            doc_domain=doc_domain,
        )
        for page_number, lines in by_page.items():
            suppress_lines[(doc_id_key, int(page_number))] = set(lines)

    # First pass: detect whether we have any headings at all.
    # If we do, REQUIREMENTS.md REQ-S3 expects every paragraph/chunk to inherit
    # a non-empty hierarchy (no empty section_path).
    doc_has_headings: Dict[str, bool] = defaultdict(bool)
    for row in rows:
        doc_id = str(row.get("doc_id", ""))
        raw_text = row.get("raw_text", "") or ""
        for ln in raw_text.splitlines():
            s = _insert_spaces_camel_case((ln or "").strip())
            if not s:
                continue
            is_h, _lvl = _detect_heading(s, doc_domain=doc_domain)
            if is_h:
                doc_has_headings[doc_id] = True
                break
        if doc_has_headings[doc_id]:
            continue

    blocks: List[Block] = []
    # Persistent state machine (per doc) as required in REQUIREMENTS.md §3.1.
    states: Dict[str, ContextState] = {}
    # Separate counters per doc to keep stable block ids.
    block_counters: Dict[str, int] = defaultdict(lambda: 1)
    global_titles: Dict[str, str | None] = defaultdict(lambda: None)

    for row in rows:
        doc_id = str(row["doc_id"])
        page_index = int(row["page_index"])
        page_number = int(row["page_number"])
        raw_text = row.get("raw_text", "") or ""

        state = states.setdefault(doc_id, ContextState())
        state.set_page(page_number)

        # If a doc has headings, ensure we always have at least a root breadcrumb.
        if doc_has_headings.get(doc_id):
            # Use known global title if we already discovered one; otherwise
            # fall back to doc_id.
            state.ensure_root(global_titles.get(doc_id) or doc_id)

        lines = raw_text.splitlines()
        para_buf: List[str] = []

        def _flush_paragraph_with_state(buf: List[str]) -> None:
            nonlocal blocks
            if not buf:
                return

            # Reconstruct paragraph text.
            lines_local = [s.strip() for s in buf if s.strip()]
            out = ""
            for ln in lines_local:
                if not out:
                    out = ln
                    continue
                if out.endswith("-") and ln and ln[0].islower():
                    out = out[:-1] + ln
                else:
                    out = out + " " + ln

            text = re.sub(r"\s+", " ", out).strip()
            if not text:
                buf.clear()
                return

            # Paragraph inherits current state (REQ-S3).
            breadcrumb_path = list(state.breadcrumb_path)
            parent_heading = breadcrumb_path[-1] if breadcrumb_path else None
            heading_level = len(breadcrumb_path) if breadcrumb_path else None

            block_id = f"{doc_id}_p{page_number:03d}_b{block_counters[doc_id]:03d}"
            blocks.append(
                Block(
                    doc_id=doc_id,
                    page_index=page_index,
                    page_number=page_number,
                    block_id=block_id,
                    block_type="paragraph",
                    heading_level=heading_level,
                    text=text,
                    parent_heading=parent_heading,
                    breadcrumb_path=breadcrumb_path,
                    heading_confidence=1.0,  # Default confidence for paragraphs
                    physical_context=None,  # TODO: Add physical context for rootless blocks
                    format_specific={"detection_method": "heuristic"},  # Format-specific metadata
                )
            )
            block_counters[doc_id] += 1
            buf.clear()

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped_raw = line.strip()
            if not stripped_raw:
                _flush_paragraph_with_state(para_buf)
                i += 1
                continue

            # 1) CamelCase repareren
            stripped = _insert_spaces_camel_case(stripped_raw)

            # Normalize "CHAPTER N Title" into "CHAPTER N — Title".
            m = re.match(r"^(CHAPTER\s+\d+)\s+(.+)$", stripped, flags=re.I)
            if m:
                stripped = f"{m.group(1).upper()} — {m.group(2).strip()}"
            m = re.match(r"^(PART\s+[IVXLC]+)\s+(.+)$", stripped, flags=re.I)
            if m:
                stripped = f"{m.group(1).upper()} — {m.group(2).strip()}"

            # 2) Paginanummers / kale nummers droppen
            if re.fullmatch(r"\d{1,4}", stripped):
                i += 1
                continue

            # 2b) Suppress running headers/footers for non-book domains.
            # Compare on normalized strings so that "8 PC World JULY 2025" and
            # "32 PC World JULY 2025" match the same suppression entry.
            sup = suppress_lines.get((doc_id, page_number))
            norm_for_sup = _normalize_running_line(stripped_raw)
            if sup and norm_for_sup and norm_for_sup in sup:
                i += 1
                continue

            # 3) Globale titel als running header op pagina's > 1 overslaan
            if (
                page_number > 1
                and global_titles.get(doc_id) is not None
                and stripped == global_titles.get(doc_id)
            ):
                i += 1
                continue

            # 4) Op de eerste paar pagina's: namen/affiliaties niet als heading
            if page_number <= 3:
                if (
                    _looks_like_person_name(stripped)
                    or _looks_like_affiliation(stripped)
                    or _looks_like_name_with_affiliation(stripped)
                ):
                    para_buf.append(stripped)
                    i += 1
                    continue

            # Merge multi-line chapter/part headings.
            merged = None
            if doc_domain == DocDomain.book:
                if re.fullmatch(r"CHAPTER\s+\d+", stripped, flags=re.I) or re.fullmatch(
                    r"PART\s+[IVXLC]+", stripped, flags=re.I
                ):
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines):
                        nxt = _insert_spaces_camel_case(lines[j].strip())
                        if _looks_like_chapter_title_candidate(nxt):
                            merged = f"{stripped} — {nxt}"
                            i = j  # will be incremented below

            if merged is not None:
                stripped = merged

            is_heading, level = _detect_heading(stripped, doc_domain=doc_domain)
            if is_heading:
                _flush_paragraph_with_state(para_buf)

                if level <= 0:
                    level = 1

                # Eerste heading op pagina 1 als globale titel bewaren
                if global_titles.get(doc_id) is None and page_number == 1:
                    global_titles[doc_id] = stripped

                # Update state machine.
                state.update_on_heading(text=stripped, level=level, page_number=page_number)
                breadcrumb_path = list(state.breadcrumb_path)
                parent_heading = breadcrumb_path[-2] if len(breadcrumb_path) >= 2 else None

                block_id = (
                    f"{doc_id}_p{page_number:03d}_b{block_counters[doc_id]:03d}"
                )
                blocks.append(
                    Block(
                        doc_id=doc_id,
                        page_index=page_index,
                        page_number=page_number,
                        block_id=block_id,
                        block_type="heading",
                        heading_level=level,
                        text=stripped,
                        parent_heading=parent_heading,
                        breadcrumb_path=breadcrumb_path,
                        heading_confidence=1.0,  # Default confidence
                        physical_context=None,  # TODO: Add physical context for rootless blocks
                        format_specific={"detection_method": "heuristic"},  # Format-specific metadata
                    )
                )
                block_counters[doc_id] += 1
            else:
                para_buf.append(stripped)

            i += 1

        _flush_paragraph_with_state(para_buf)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for block in blocks:
            f.write(json.dumps(asdict(block), ensure_ascii=False) + "\n")

    # QA-3: write a lightweight structure report for visual verification.
    try:
        report_path = out_path.parent / "structure_report.txt"
        lines_out: List[str] = []
        for b in blocks:
            if b.block_type != "heading":
                continue
            indent = "  " * max(0, int(b.heading_level or 1) - 1)
            crumbs = " > ".join(b.breadcrumb_path)
            lines_out.append(f"p{b.page_number:03d} {indent}{b.text} | {crumbs}")
        report_path.write_text("\n".join(lines_out) + ("\n" if lines_out else ""), encoding="utf-8")
    except Exception:
        # Report is best-effort; do not fail conversion.
        pass

    return out_path
