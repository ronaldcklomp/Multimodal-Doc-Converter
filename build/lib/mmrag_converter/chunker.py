from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List

from .doc_profile import DocDomain


# Allow a small overflow so we can finish a sentence. This is intentionally
# conservative: we still enforce a hard ceiling via secondary splitting when
# a single segment would otherwise exceed the limit.
CHUNK_SLACK_TOKENS = 20


@dataclass
class TextChunk:
    doc_id: str
    chunk_id: str
    page_start: int
    page_end: int
    text: str
    tokens_estimate: int
    parent_heading: str | None
    heading_level: int | None
    # REQUIREMENTS.md §3.1
    breadcrumb_path: List[str]
    modality: str = "text"


def _estimate_tokens(text: str) -> int:
    """
    Ruwe schatting van tokens: ~1.3 * aantal woorden.
    """
    words = text.split()
    return int(len(words) * 13 / 10)


def _cleanup_chunk_text(text: str) -> str:
    """Normalize extracted text for RAG.

    - collapse whitespace
    - fix common hyphenation artifacts
    """
    t = (text or "").strip()
    if not t:
        return ""
    # fix hyphenation that may remain after paragraph reconstruction
    t = t.replace("- ", "")
    t = " ".join(t.split())
    return t


_SENT_BOUNDARY_RE = re.compile(
    # Split on end-of-sentence punctuation followed by whitespace and a
    # plausible sentence start.
    r"(?<=[.!?])\s+(?=[A-Z0-9\"\(\[])",
)


_RELAXED_SENT_BOUNDARY_RE = re.compile(
    # Fallback splitter used only when a single segment becomes too large.
    #
    # Supports:
    # - lowercase sentence starts (common in OCR/EPUB artifacts): "... . next"
    # - missing whitespace after punctuation (common extraction artifact): "... .Next"
    # 1) Standard: punctuation + whitespace (allow lowercase sentence starts).
    # 2) Fallback: punctuation with missing whitespace, but only when the
    #    punctuation is preceded by a letter to avoid splitting decimals (3.14).
    r"(?<=[.!?])\s+(?=[A-Za-z0-9\"\(\[])")


_RELAXED_SENT_BOUNDARY_RE_2 = re.compile(
    r"(?<=[A-Za-z][.!?])(?=[A-Z0-9\"\(\[])",
)


def _split_sentences(text: str) -> List[str]:
    t = _cleanup_chunk_text(text)
    if not t:
        return []
    # If there is no clear sentence punctuation, return as a single segment.
    if not re.search(r"[.!?]", t):
        return [t]
    parts = _SENT_BOUNDARY_RE.split(t)
    return [p.strip() for p in parts if p and p.strip()]


def _split_sentences_relaxed(text: str) -> List[str]:
    """More permissive sentence split.

    Only used as a fallback when the default splitter yields a huge segment.
    """

    t = _cleanup_chunk_text(text)
    if not t:
        return []
    if not re.search(r"[.!?]", t):
        return [t]
    parts = _RELAXED_SENT_BOUNDARY_RE.split(t)
    # Second-pass split for missing whitespace after punctuation.
    out: List[str] = []
    for p in parts:
        if not p or not p.strip():
            continue
        out.extend(_RELAXED_SENT_BOUNDARY_RE_2.split(p))
    return [p.strip() for p in out if p and p.strip()]


def _split_by_token_budget(text: str, budget_tokens: int) -> List[str]:
    """Hard-split text into segments that each fit within budget_tokens.

    This is the final safety net for pathological cases (very long 'sentences'
    such as link lists, or punctuation artifacts) where sentence boundaries are
    insufficient.
    """

    t = _cleanup_chunk_text(text)
    if not t:
        return []

    # Greedy word packing using the same estimator.
    words = t.split()
    out: List[str] = []
    buf: List[str] = []

    def flush() -> None:
        if buf:
            out.append(" ".join(buf).strip())
            buf.clear()

    for w in words:
        cand = (" ".join(buf + [w])).strip()
        if not cand:
            continue
        if _estimate_tokens(cand) <= budget_tokens:
            buf.append(w)
            continue
        # Flush what we have.
        flush()
        # Single word can still overflow (extremely long URL/token). Keep it.
        buf.append(w)
        flush()

    flush()
    return [s for s in out if s]


def _split_segment_to_budget(text: str, budget_tokens: int) -> List[str]:
    """Split a 'sentence' (or sentence-like segment) to fit within budget.

    Tries increasingly aggressive boundaries:
    1) semicolons/colons
    2) commas
    3) before URLs
    4) word-budget split (hard fallback)
    """

    t = _cleanup_chunk_text(text)
    if not t:
        return []
    if _estimate_tokens(t) <= budget_tokens:
        return [t]

    # Clause-like boundaries.
    for rx in (
        re.compile(r"(?<=[;:])\s+"),
        re.compile(r"(?<=,)\s+"),
        re.compile(r"\s+(?=https?://)"),
    ):
        parts = [p.strip() for p in rx.split(t) if p and p.strip()]
        if len(parts) <= 1:
            continue
        # If this boundary helps, recurse per part.
        if max((_estimate_tokens(p) for p in parts), default=0) < _estimate_tokens(t):
            out: List[str] = []
            for p in parts:
                out.extend(_split_segment_to_budget(p, budget_tokens))
            # If we actually improved, return.
            out_max = max((_estimate_tokens(p) for p in out))
            parts_max = max((_estimate_tokens(p) for p in parts))
            if out and out_max <= parts_max:
                return out

    return _split_by_token_budget(t, budget_tokens)


def _looks_like_continuation(prev: str, nxt: str) -> bool:
    """Heuristic: paragraph split that is likely a hard line/column break."""
    a = (prev or "").strip()
    b = (nxt or "").strip()
    if not a or not b:
        return False
    if a.endswith("-") and b and b[0].islower():
        return True
    if not re.search(r"[.!?]\s*$", a) and b and b[0].islower():
        return True
    # When the previous ends with a preposition/connector, and the next begins
    # with a lowercase continuation, treat it as a soft wrap.
    if (
        b
        and b[0].islower()
        and re.search(
            r"\b(from|to|of|in|on|for|with|and|or|as|at|by)\s*$",
            a,
            flags=re.I,
        )
    ):
        return True
    return False


def _split_into_smaller_chunks(text: str, max_tokens: int) -> List[str]:
    """Split a long text into smaller chunks on paragraph boundaries.

    This is a safety-net for cases where a single extracted paragraph is huge
    (e.g., ToC or long code blocks) and would otherwise violate max_tokens.
    """

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    out: List[str] = []
    buf: List[str] = []

    def flush() -> None:
        if buf:
            out.append("\n\n".join(buf))
            buf.clear()

    for para in paragraphs:
        candidate = ("\n\n".join(buf + [para])).strip()
        if not candidate:
            continue
        if _estimate_tokens(candidate) <= max_tokens:
            buf.append(para)
            continue

        # If adding this paragraph exceeds, flush what we have.
        flush()

        # If the single paragraph itself is too large, split by lines.
        if _estimate_tokens(para) > max_tokens:
            lines = [ln.strip() for ln in para.splitlines() if ln.strip()]
            line_buf: List[str] = []
            for ln in lines:
                cand = ("\n".join(line_buf + [ln])).strip()
                if _estimate_tokens(cand) <= max_tokens:
                    line_buf.append(ln)
                else:
                    if line_buf:
                        out.append("\n".join(line_buf))
                        line_buf = [ln]
                    else:
                        # Extreme edge case: a single line is huge.
                        out.append(ln)
                        line_buf = []
            if line_buf:
                out.append("\n".join(line_buf))
        else:
            buf.append(para)

    flush()
    return out


def _load_blocks(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    rows.sort(key=lambda r: (r["page_number"], r["block_id"]))
    return rows


def chunk_blocks_to_jsonl(
    blocks_path: Path,
    out_path: Path,
    max_tokens: int = 400,
    min_tokens: int = 30,
    dedup_exact_text: bool = True,
    doc_domain: DocDomain = DocDomain.book,
) -> Path:
    """
    Neem blocks_structured.jsonl en maak RAG-vriendelijke tekstchunks.
    """
    blocks = _load_blocks(blocks_path)
    if not blocks:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.touch()
        return out_path

    doc_id = str(blocks[0].get("doc_id", ""))

    chunks: List[TextChunk] = []

    current_heading: str | None = None
    current_heading_level: int | None = None
    current_breadcrumb_path: List[str] = []

    # Buffer paragraphs (with page provenance) so we can split semantically.
    buffer_items: List[Dict[str, Any]] = []  # {page_start,page_end,text}
    buffer_page_start = 0
    buffer_page_end = 0
    buffer_parent_heading: str | None = None
    buffer_heading_level: int | None = None
    buffer_breadcrumb_path: List[str] = []
    buffer_tokens = 0
    chunk_index = 1

    def flush_buffer() -> None:
        nonlocal chunk_index
        nonlocal buffer_items, buffer_page_start, buffer_page_end
        nonlocal buffer_parent_heading, buffer_heading_level
        nonlocal buffer_breadcrumb_path, buffer_tokens

        if not buffer_items:
            return

        # 1) Merge paragraph items that are likely split by hard line breaks.
        merged: List[Dict[str, Any]] = []
        for it in buffer_items:
            t = _cleanup_chunk_text(str(it.get("text") or ""))
            if not t:
                continue
            if merged and _looks_like_continuation(merged[-1]["text"], t):
                merged[-1]["text"] = _cleanup_chunk_text(
                    merged[-1]["text"].rstrip("-") + " " + t
                )
                merged[-1]["page_end"] = max(
                    int(merged[-1]["page_end"]),
                    int(it.get("page_end", it.get("page_start", 0))),
                )
            else:
                merged.append(
                    {
                        "page_start": int(it.get("page_start", 0)),
                        "page_end": int(it.get("page_end", 0)),
                        "text": t,
                    }
                )

        if not merged:
            buffer_items = []
            buffer_page_start = 0
            buffer_page_end = 0
            buffer_parent_heading = None
            buffer_heading_level = None
            buffer_breadcrumb_path = []
            buffer_tokens = 0
            return

        # 2) Split into chunks at sentence boundaries.
        prefix = ""
        if buffer_parent_heading:
            prefix = buffer_parent_heading.strip() + "\n\n"

        slack = CHUNK_SLACK_TOKENS  # allow slight overflow to finish a sentence
        cur_sentences: List[str] = []
        cur_page_start: int | None = None
        cur_page_end: int | None = None

        prefix_tok = _estimate_tokens(prefix) if prefix else 0
        budget = max(1, (max_tokens + slack) - prefix_tok)

        def _emit_chunk(body: str, ps: int, pe: int) -> None:
            """Append one or more chunks for a body, enforcing max token budget."""

            nonlocal chunk_index

            b = _cleanup_chunk_text(body)
            if not b:
                return

            # Enforce ceiling; hard-split if needed.
            # Note: we split the *body* (without prefix), but budget accounts for prefix.
            parts = [b]
            if _estimate_tokens((prefix + b).strip() if prefix else b) > (max_tokens + slack):
                parts = _split_segment_to_budget(b, budget)

            for part in parts:
                if not part:
                    continue
                text = (prefix + part).strip() if prefix else part
                tok = _estimate_tokens(text)
                # As a final safety net, ensure the estimator doesn't drift.
                if tok > max_tokens + slack:
                    tighter = max(1, (max_tokens + slack) - (prefix_tok if prefix else 0))
                    for p2 in _split_by_token_budget(part, tighter):
                        text2 = (prefix + p2).strip() if prefix else p2
                        tok2 = _estimate_tokens(text2)
                        if tok2 < min_tokens:
                            continue
                        chunk_id = f"{doc_id}_c{chunk_index:04d}"
                        chunks.append(
                            TextChunk(
                                doc_id=doc_id,
                                chunk_id=chunk_id,
                                page_start=int(ps),
                                page_end=int(pe),
                                text=text2,
                                tokens_estimate=tok2,
                                parent_heading=buffer_parent_heading,
                                heading_level=buffer_heading_level,
                                breadcrumb_path=list(buffer_breadcrumb_path),
                            )
                        )
                        chunk_index += 1
                    continue

                if tok < min_tokens:
                    continue

                chunk_id = f"{doc_id}_c{chunk_index:04d}"
                chunks.append(
                    TextChunk(
                        doc_id=doc_id,
                        chunk_id=chunk_id,
                        page_start=int(ps),
                        page_end=int(pe),
                        text=text,
                        tokens_estimate=tok,
                        parent_heading=buffer_parent_heading,
                        heading_level=buffer_heading_level,
                        breadcrumb_path=list(buffer_breadcrumb_path),
                    )
                )
                chunk_index += 1

        def flush_chunk() -> None:
            nonlocal cur_sentences, cur_page_start, cur_page_end
            if not cur_sentences:
                return

            body = " ".join(cur_sentences).strip()
            if not body:
                cur_sentences = []
                cur_page_start = None
                cur_page_end = None
                return

            _emit_chunk(
                body,
                int(cur_page_start or buffer_page_start),
                int(cur_page_end or buffer_page_end),
            )

            cur_sentences = []
            cur_page_start = None
            cur_page_end = None

        for it in merged:
            ps = int(it["page_start"])
            pe = int(it["page_end"])
            sentences = _split_sentences(it["text"])

            # If we detect missing whitespace after punctuation inside a
            # sentence ("...limit.This is...") then the strict splitter can
            # merge multiple sentences into one, which then forces hard token
            # splitting and may break sentences mid-way. Re-split using the
            # relaxed splitter in that case.
            if any(
                re.search(r"[A-Za-z][.!?][A-Z0-9\"\(\[]", s or "")
                for s in sentences
            ):
                sentences = _split_sentences_relaxed(it["text"])

            # If the default splitter yields a huge segment, try a more
            # permissive splitter to avoid pathological oversize chunks.
            first_sent_tokens = _estimate_tokens(
                (prefix + sentences[0]).strip() if prefix else sentences[0]
            )
            if len(sentences) == 1 and first_sent_tokens > (max_tokens + slack):
                sentences = _split_sentences_relaxed(it["text"])
            if not sentences:
                continue

            for sent in sentences:
                # Ensure each atomic segment fits within the per-chunk budget.
                segments = _split_segment_to_budget(sent, budget)
                for seg in segments:
                    cand_body = " ".join(cur_sentences + [seg]).strip()
                    cand_text = (prefix + cand_body).strip() if prefix else cand_body
                    cand_tok = _estimate_tokens(cand_text)

                    if cur_sentences:
                        ends_sentence = bool(re.search(r"[.!?]\s*$", seg))
                        if cand_tok > max_tokens and not (
                            ends_sentence and cand_tok <= max_tokens + slack
                        ):
                            flush_chunk()
                            cand_body = seg
                            cand_text = (
                                (prefix + cand_body).strip() if prefix else cand_body
                            )
                            cand_tok = _estimate_tokens(cand_text)

                    # Still too large? This can happen if a segment is huge and the
                    # prefix consumes most of the budget. In that case we emit it
                    # via the hard budget splitter.
                    if cand_tok > max_tokens + slack:
                        flush_chunk()
                        _emit_chunk(seg, ps, pe)
                        continue

                    cur_sentences.append(seg)
                    if cur_page_start is None:
                        cur_page_start = ps
                    cur_page_end = pe

        flush_chunk()

        buffer_items = []
        buffer_page_start = 0
        buffer_page_end = 0
        buffer_parent_heading = None
        buffer_heading_level = None
        buffer_breadcrumb_path = []
        buffer_tokens = 0

    for block in blocks:
        block_type = block.get("block_type")
        if block_type == "heading":
            flush_buffer()
            current_heading = (block.get("text") or "").strip() or None
            current_heading_level = block.get("heading_level")
            current_breadcrumb_path = (
                block.get("breadcrumb_path")
                or block.get("section_path")
                or []
            )
            continue

        if block_type != "paragraph":
            continue

        para_text = (block.get("text") or "").strip()
        if not para_text:
            continue

        # Domain-specific lightweight cleanup.
        # Academic PDFs often contain huge ToC/List-of-Figures pages which are
        # low-value for retrieval.
        if doc_domain == DocDomain.academic:
            lowered = para_text.lower()
            if (
                lowered.startswith("contents")
                or lowered.startswith("list of figures")
            ):
                continue

        page_number = int(block["page_number"])

        # Ensure we always inherit an active hierarchy when it's present.
        # Some docs have paragraph-ish content before the first detected
        # heading; the structure analyzer will still set breadcrumb_path.
        bcrumb = list(block.get("breadcrumb_path") or block.get("section_path") or [])

        if not buffer_items:
            buffer_page_start = page_number
            buffer_page_end = page_number
            buffer_breadcrumb_path = list(current_breadcrumb_path or bcrumb)
            if current_heading:
                buffer_parent_heading = current_heading
            elif buffer_breadcrumb_path:
                buffer_parent_heading = buffer_breadcrumb_path[-1]
            else:
                buffer_parent_heading = None
            buffer_heading_level = current_heading_level
            if buffer_heading_level is None and buffer_breadcrumb_path:
                buffer_heading_level = len(buffer_breadcrumb_path)

        buffer_items.append(
            {
                "page_start": page_number,
                "page_end": page_number,
                "text": para_text,
            }
        )
        buffer_page_end = page_number
        buffer_tokens += _estimate_tokens(para_text)

        # Flush only when the buffer becomes very large; chunking happens
        # inside flush_buffer() at sentence boundaries.
        if buffer_tokens >= max_tokens * 6:
            flush_buffer()
    flush_buffer()

    if dedup_exact_text and chunks:
        seen: set[str] = set()
        deduped: List[TextChunk] = []
        for ch in chunks:
            key = ch.text.strip()
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            deduped.append(ch)
        chunks = deduped

    # Drop remaining tiny chunks at the end (often noise). Keep at least one.
    if min_tokens > 0 and chunks:
        filtered = [c for c in chunks if c.tokens_estimate >= min_tokens]
        if filtered:
            chunks = filtered

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for ch in chunks:
            f.write(json.dumps(asdict(ch), ensure_ascii=False) + "\n")

    return out_path
