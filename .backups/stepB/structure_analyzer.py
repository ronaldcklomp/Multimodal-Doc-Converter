from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .doc_profile import DocDomain


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
    section_path: List[str]


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

    # Appendix-style headings: "A", "A.1", "B.5".
    if re.fullmatch(r"[A-Z](?:\.\d+)*", line.strip()):
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


def _flush_paragraph(
    buffer: List[str],
    blocks: List[Block],
    doc_id: str,
    page_index: int,
    page_number: int,
    block_counter: int,
    current_section: List[Tuple[int, str]],
) -> int:
    if not buffer:
        return block_counter

    # Bewaar linebreaks binnen een paragraaf.
    lines = [s.strip() for s in buffer if s.strip()]
    text = "\n".join(lines)
    if not text:
        return block_counter

    if current_section:
        parent_level, parent_text = current_section[-1]
        section_path = [h[1] for h in current_section]
    else:
        parent_level = 0
        parent_text = None
        section_path = []

    block_id = f"{doc_id}_p{page_number:03d}_b{block_counter:03d}"
    blocks.append(
        Block(
            doc_id=doc_id,
            page_index=page_index,
            page_number=page_number,
            block_id=block_id,
            block_type="paragraph",
            heading_level=parent_level,
            text=text,
            parent_heading=parent_text,
            section_path=section_path,
        )
    )
    buffer.clear()
    return block_counter + 1


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

    blocks: List[Block] = []
    current_section: List[Tuple[int, str]] = []
    block_counter = 1
    global_title: str | None = None

    for row in rows:
        doc_id = row["doc_id"]
        page_index = row["page_index"]
        page_number = row["page_number"]
        raw_text = row.get("raw_text", "") or ""

        lines = raw_text.splitlines()
        para_buf: List[str] = []

        for line in lines:
            stripped_raw = line.strip()
            if not stripped_raw:
                block_counter = _flush_paragraph(
                    para_buf,
                    blocks,
                    doc_id,
                    page_index,
                    page_number,
                    block_counter,
                    current_section,
                )
                continue

            # 1) CamelCase repareren
            stripped = _insert_spaces_camel_case(stripped_raw)

            # 2) Paginanummers / kale nummers droppen
            if re.fullmatch(r"\d{1,4}", stripped):
                continue

            # 3) Globale titel als running header op pagina's > 1 overslaan
            if (
                page_number > 1
                and global_title is not None
                and stripped == global_title
            ):
                continue

            # 4) Op de eerste paar pagina's: namen/affiliaties niet als heading
            if page_number <= 3:
                if (
                    _looks_like_person_name(stripped)
                    or _looks_like_affiliation(stripped)
                    or _looks_like_name_with_affiliation(stripped)
                ):
                    para_buf.append(stripped)
                    continue

            is_heading, level = _detect_heading(
                stripped,
                doc_domain=doc_domain,
            )
            if is_heading:
                block_counter = _flush_paragraph(
                    para_buf,
                    blocks,
                    doc_id,
                    page_index,
                    page_number,
                    block_counter,
                    current_section,
                )

                if level <= 0:
                    level = 1

                # Eerste heading op pagina 1 als globale titel bewaren
                if global_title is None and page_number == 1:
                    global_title = stripped

                current_section = [
                    h for h in current_section if h[0] < level
                ]
                current_section.append((level, stripped))
                section_path = [h[1] for h in current_section]

                block_id = (
                    f"{doc_id}_p{page_number:03d}_b{block_counter:03d}"
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
                        parent_heading=None,
                        section_path=section_path,
                    )
                )
                block_counter += 1
            else:
                para_buf.append(stripped)

        block_counter = _flush_paragraph(
            para_buf,
            blocks,
            doc_id,
            page_index,
            page_number,
            block_counter,
            current_section,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for block in blocks:
            f.write(json.dumps(asdict(block), ensure_ascii=False) + "\n")

    return out_path
