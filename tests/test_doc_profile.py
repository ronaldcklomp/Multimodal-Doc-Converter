import unittest

from mmrag_converter.doc_profile import DocDomain, detect_doc_domain


class TestDetectDocDomain(unittest.TestCase):
    def test_academic_keywords(self) -> None:
        text = """
        Abstract
        This paper presents ...
        References
        """
        domain, signals = detect_doc_domain(
            text,
            pdf_metadata={"creator": "LaTeX", "producer": "pdfTeX"},
        )
        self.assertEqual(domain, DocDomain.academic)
        self.assertGreaterEqual(signals["scores"]["academic"], 1)

    def test_manual_keywords(self) -> None:
        text = """
        User Guide
        Installation
        Troubleshooting
        """
        domain, _ = detect_doc_domain(text, pdf_metadata={})
        self.assertEqual(domain, DocDomain.manual)

    def test_default_book(self) -> None:
        # No strong keywords -> defaults to book
        domain, _ = detect_doc_domain("Hello world", pdf_metadata={})
        self.assertEqual(domain, DocDomain.book)
