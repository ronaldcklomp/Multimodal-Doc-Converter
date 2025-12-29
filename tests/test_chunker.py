import json
import tempfile
import unittest
from pathlib import Path

from mmrag_converter.chunker import chunk_blocks_to_jsonl
from mmrag_converter.doc_profile import DocDomain


class TestChunker(unittest.TestCase):
    def test_dedup_exact_text(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            blocks = tmp / "blocks.jsonl"
            out = tmp / "chunks.jsonl"

            # Two identical paragraphs under same heading => should dedup.
            rows = [
                {
                    "doc_id": "d",
                    "page_number": 1,
                    "block_id": "b001",
                    "block_type": "heading",
                    "heading_level": 1,
                    "text": "Intro",
                    "section_path": ["Intro"],
                },
                {
                    "doc_id": "d",
                    "page_number": 1,
                    "block_id": "b002",
                    "block_type": "paragraph",
                    "text": "Same text paragraph.",
                },
                {
                    "doc_id": "d",
                    "page_number": 1,
                    "block_id": "b003",
                    "block_type": "paragraph",
                    "text": "Same text paragraph.",
                },
            ]
            blocks.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

            chunk_blocks_to_jsonl(
                blocks_path=blocks,
                out_path=out,
                max_tokens=400,
                min_tokens=1,
                dedup_exact_text=True,
                doc_domain=DocDomain.book,
            )

            with out.open("r", encoding="utf-8") as f:
                chunks = [json.loads(line) for line in f if line.strip()]
            self.assertEqual(len(chunks), 1)

    def test_min_tokens_filters_small(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            blocks = tmp / "blocks.jsonl"
            out = tmp / "chunks.jsonl"

            rows = [
                {
                    "doc_id": "d",
                    "page_number": 1,
                    "block_id": "b001",
                    "block_type": "paragraph",
                    "text": "tiny",
                },
                {
                    "doc_id": "d",
                    "page_number": 1,
                    "block_id": "b002",
                    "block_type": "paragraph",
                    "text": "This is a longer paragraph with enough words to pass the threshold.",
                },
            ]
            blocks.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

            chunk_blocks_to_jsonl(
                blocks_path=blocks,
                out_path=out,
                max_tokens=400,
                min_tokens=10,
                dedup_exact_text=False,
                doc_domain=DocDomain.book,
            )

            with out.open("r", encoding="utf-8") as f:
                chunks = [json.loads(line) for line in f if line.strip()]
            # Only the longer chunk should remain.
            self.assertEqual(len(chunks), 1)
            self.assertIn("longer paragraph", chunks[0]["text"])

    def test_no_mid_sentence_split_when_exceeding_max_tokens(self) -> None:
        """If a single paragraph would exceed max_tokens, we should split on
        sentence boundaries when possible, not mid-sentence.

        This protects against common PDF column-wrap artifacts that otherwise
        blow up RAG quality.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            blocks = tmp / "blocks.jsonl"
            out = tmp / "chunks.jsonl"

            para = (
                "This is the second sentence with a bit more words to push "
                "the token count. "
                "This is the third sentence with even more words to make "
                "the chunk exceed the limit."
                "This is the third sentence with even more words to make the chunk exceed the \
                    limit."
            )
            rows = [
                {
                    "doc_id": "d",
                    "page_number": 1,
                    "block_id": "b001",
                    "block_type": "paragraph",
                    "text": para,
                }
            ]
            blocks.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )

            # Very small max_tokens to force a split.
            chunk_blocks_to_jsonl(
                blocks_path=blocks,
                out_path=out,
                max_tokens=15,
                min_tokens=1,
                dedup_exact_text=False,
                doc_domain=DocDomain.book,
            )

            with out.open("r", encoding="utf-8") as f:
                chunks = [json.loads(line) for line in f if line.strip()]

            self.assertGreaterEqual(len(chunks), 2)
            # Every chunk should end at a sentence boundary (., !, ?).
            for ch in chunks:
                self.assertRegex(ch["text"].strip(), r"[.!?]$")

    def test_hard_enforces_max_tokens_for_pathological_long_segments(self) -> None:
        """When text contains very long segments (e.g., link lists) that don't
        split well into sentences, we still must enforce max_tokens(+slack).

        This protects downstream embedding/ingestion which often has strict
        token limits.
        """

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            blocks = tmp / "blocks.jsonl"
            out = tmp / "chunks.jsonl"

            # Create a single paragraph with many URLs and commas.
            # This tends to produce very long "sentences" in real docs.
            urls = [f"https://example.com/resource/{i}" for i in range(200)]
            para = "Sources and links: " + ", ".join(urls) + "."

            rows = [
                {
                    "doc_id": "d",
                    "page_number": 1,
                    "block_id": "b001",
                    "block_type": "paragraph",
                    "text": para,
                }
            ]
            blocks.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )

            max_tokens = 80
            chunk_blocks_to_jsonl(
                blocks_path=blocks,
                out_path=out,
                max_tokens=max_tokens,
                min_tokens=1,
                dedup_exact_text=False,
                doc_domain=DocDomain.book,
            )

            with out.open("r", encoding="utf-8") as f:
                chunks = [json.loads(line) for line in f if line.strip()]

            self.assertGreaterEqual(len(chunks), 2)

            # Hard cap must hold for all chunks (allowing slack).
            for ch in chunks:
                self.assertLessEqual(int(ch["tokens_estimate"]), max_tokens + 20)
