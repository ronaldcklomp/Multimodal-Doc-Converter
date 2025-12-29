import unittest

from mmrag_converter.structure_analyzer import _detect_heading
from mmrag_converter.doc_profile import DocDomain


class TestEpubHeadingHeuristics(unittest.TestCase):
    def test_postal_code_not_heading(self) -> None:
        # Example seen in small_sample.epub colophon
        is_heading, _ = _detect_heading(
            "16341 Panketal",
            doc_domain=DocDomain.book,
        )
        self.assertFalse(is_heading)

    def test_hoofdstuk_heading(self) -> None:
        is_heading, level = _detect_heading(
            "Hoofdstuk 1: Fundamenten en doelstellingen",
            doc_domain=DocDomain.book,
        )
        self.assertTrue(is_heading)
        self.assertEqual(level, 1)
