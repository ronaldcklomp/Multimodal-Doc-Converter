import json
import tempfile
import unittest
from pathlib import Path


from mmrag_converter.structure_analyzer import analyze_text_structure
from mmrag_converter.chunker import chunk_blocks_to_jsonl
from mmrag_converter.doc_profile import DocDomain


class TestPersistentStateMachine(unittest.TestCase):
    def test_paragraph_inherits_breadcrumb_when_headings_exist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pages = tmp / "pages_raw.jsonl"
            out_blocks = tmp / "blocks.jsonl"

            # Page 1 contains a heading line, so all paragraphs should inherit.
            rows = [
                {
                    "doc_id": "d",
                    "page_index": 0,
                    "page_number": 1,
                    "raw_text": "CHAPTER 1\n\nThis is paragraph one.",
                    "is_scanned_like": False,
                },
                {
                    "doc_id": "d",
                    "page_index": 1,
                    "page_number": 2,
                    "raw_text": "This is paragraph two on the next page.",
                    "is_scanned_like": False,
                },
            ]
            pages.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

            analyze_text_structure(
                in_path=pages,
                out_path=out_blocks,
                doc_domain=DocDomain.book,
            )

            blocks = [
                json.loads(ln)
                for ln in out_blocks.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            paras = [b for b in blocks if b.get("block_type") == "paragraph"]
            self.assertGreaterEqual(len(paras), 2)
            for p in paras:
                self.assertIn("breadcrumb_path", p)
                self.assertTrue(p["breadcrumb_path"], "breadcrumb_path should not be empty")

    def test_chunk_inherits_breadcrumb(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            blocks = tmp / "blocks.jsonl"
            chunks = tmp / "chunks.jsonl"

            rows = [
                {
                    "doc_id": "d",
                    "page_number": 1,
                    "block_id": "b001",
                    "block_type": "heading",
                    "heading_level": 1,
                    "text": "Intro",
                    "breadcrumb_path": ["Intro"],
                },
                {
                    "doc_id": "d",
                    "page_number": 1,
                    "block_id": "b002",
                    "block_type": "paragraph",
                    "text": "This is a paragraph with enough words to pass the threshold.",
                    "breadcrumb_path": ["Intro"],
                },
            ]
            blocks.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

            chunk_blocks_to_jsonl(
                blocks_path=blocks,
                out_path=chunks,
                max_tokens=400,
                min_tokens=1,
                dedup_exact_text=False,
                doc_domain=DocDomain.book,
            )

            out = [
                json.loads(ln)
                for ln in chunks.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0].get("breadcrumb_path"), ["Intro"])
