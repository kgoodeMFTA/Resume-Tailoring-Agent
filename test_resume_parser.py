"""
Unit tests for agent.resume_parser.ResumeParser.

Tests cover:
  - PDF text extraction (mocked via pdfplumber)
  - DOCX text extraction (mocked via python-docx)
  - Structured field parsing (name, email, phone, sections)
  - Graceful handling of missing fields
  - Unsupported file format error
  - File not found error
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, mock_open, patch

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.resume_parser import ResumeParser


# ---------------------------------------------------------------------------
# Sample resume text used across multiple tests
# ---------------------------------------------------------------------------
SAMPLE_RESUME_TEXT = """Jane Doe
jane.doe@example.com
+1 (555) 123-4567

Summary
Experienced software engineer with 8 years building distributed systems at scale.
Passionate about open-source and developer tooling.

Experience
Senior Software Engineer | Acme Corp | Jan 2020 – Present
- Led migration of monolithic service to microservices, reducing latency by 40%
- Designed event-driven pipeline processing 1M+ messages/day on Apache Kafka
- Mentored 4 junior engineers and introduced code review best practices

Software Engineer | StartupXYZ | Jun 2017 – Dec 2019
- Built REST APIs serving 500K daily active users using FastAPI and PostgreSQL
- Reduced CI/CD pipeline runtime by 60% through parallelisation and caching

Education
Bachelor of Science in Computer Science 2017
University of California, Berkeley

Skills
Python, Go, Kubernetes, Docker, Kafka, PostgreSQL, Redis, AWS, Terraform

Certifications
AWS Certified Solutions Architect – Associate
Certified Kubernetes Administrator (CKA)
"""


class TestResumeParserInit(unittest.TestCase):
    """Test instantiation behaviour."""

    def test_default_logger_created(self):
        parser = ResumeParser()
        self.assertIsNotNone(parser.logger)

    def test_custom_logger_accepted(self):
        import logging
        custom = logging.getLogger("test_custom")
        parser = ResumeParser(logger=custom)
        self.assertEqual(parser.logger, custom)


class TestResumeParserFileErrors(unittest.TestCase):
    """Test file-level error handling."""

    def setUp(self):
        self.parser = ResumeParser()

    def test_file_not_found_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.parser.parse("/non/existent/path/resume.pdf")

    def test_unsupported_extension_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"dummy text")
            tmp_path = f.name
        try:
            with self.assertRaises(ValueError) as ctx:
                self.parser.parse(tmp_path)
            self.assertIn("Unsupported", str(ctx.exception))
        finally:
            os.unlink(tmp_path)


class TestResumePDFParse(unittest.TestCase):
    """Test PDF parsing path (pdfplumber mocked)."""

    def setUp(self):
        self.parser = ResumeParser()

    @patch("agent.resume_parser.pdfplumber")
    def test_pdf_parse_returns_dict(self, mock_pdfplumber):
        """Verify that a mocked PDF produces a valid resume dict."""
        # Configure mock pdfplumber context manager
        mock_page = MagicMock()
        mock_page.extract_text.return_value = SAMPLE_RESUME_TEXT

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdfplumber.open.return_value = mock_pdf

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 dummy")
            tmp_path = f.name

        try:
            result = self.parser.parse(tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertIsInstance(result, dict)
        self._assert_resume_keys(result)

    @patch("agent.resume_parser.pdfplumber")
    def test_pdf_extracts_email(self, mock_pdfplumber):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = SAMPLE_RESUME_TEXT
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdfplumber.open.return_value = mock_pdf

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 dummy")
            tmp_path = f.name

        try:
            result = self.parser.parse(tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertEqual(result["email"], "jane.doe@example.com")

    @patch("agent.resume_parser.pdfplumber")
    def test_pdf_extracts_skills_list(self, mock_pdfplumber):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = SAMPLE_RESUME_TEXT
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdfplumber.open.return_value = mock_pdf

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 dummy")
            tmp_path = f.name

        try:
            result = self.parser.parse(tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertIsInstance(result["skills"], list)
        self.assertGreater(len(result["skills"]), 0)

    def test_pdf_no_pdfplumber_raises(self):
        """If pdfplumber is None (not installed) parsing PDF should raise RuntimeError."""
        original = __import__("agent.resume_parser", fromlist=["resume_parser"]).pdfplumber
        import agent.resume_parser as rp
        rp.pdfplumber = None

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 dummy")
            tmp_path = f.name

        try:
            with self.assertRaises(RuntimeError) as ctx:
                self.parser._extract_pdf_text(tmp_path)
            self.assertIn("pdfplumber", str(ctx.exception))
        finally:
            rp.pdfplumber = original
            os.unlink(tmp_path)

    def _assert_resume_keys(self, result: dict):
        expected_keys = [
            "name", "email", "phone", "summary",
            "experience", "education", "skills", "certifications", "raw_text"
        ]
        for key in expected_keys:
            self.assertIn(key, result, f"Missing key: {key}")


class TestResumeDOCXParse(unittest.TestCase):
    """Test DOCX parsing path (python-docx mocked)."""

    def setUp(self):
        self.parser = ResumeParser()

    @patch("agent.resume_parser.DocxDocument")
    def test_docx_parse_returns_dict(self, mock_docx_cls):
        """Verify that a mocked DOCX produces a valid resume dict."""
        paragraphs = [MagicMock(text=line) for line in SAMPLE_RESUME_TEXT.splitlines()]
        mock_doc = MagicMock()
        mock_doc.paragraphs = paragraphs
        mock_docx_cls.return_value = mock_doc

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"PK dummy docx content")
            tmp_path = f.name

        try:
            result = self.parser.parse(tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertIsInstance(result, dict)
        self.assertIn("name", result)
        self.assertIn("experience", result)

    @patch("agent.resume_parser.DocxDocument")
    def test_docx_handles_empty_paragraphs(self, mock_docx_cls):
        """Empty paragraphs should be silently skipped."""
        paragraphs = [MagicMock(text=""), MagicMock(text="  "), MagicMock(text="Jane Doe")]
        mock_doc = MagicMock()
        mock_doc.paragraphs = paragraphs
        mock_docx_cls.return_value = mock_doc

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"PK dummy docx content")
            tmp_path = f.name

        try:
            result = self.parser.parse(tmp_path)
        finally:
            os.unlink(tmp_path)

        self.assertIsInstance(result, dict)


class TestResumeParserFieldExtraction(unittest.TestCase):
    """Test low-level field extraction methods."""

    def setUp(self):
        self.parser = ResumeParser()

    def test_extract_email(self):
        text = "Contact me at alex.smith+work@domain.co.uk for more info."
        self.assertEqual(self.parser._extract_email(text), "alex.smith+work@domain.co.uk")

    def test_extract_email_missing(self):
        self.assertEqual(self.parser._extract_email("No email here."), "")

    def test_extract_phone_us(self):
        text = "Phone: (415) 555-0192"
        phone = self.parser._extract_phone(text)
        self.assertIn("415", phone)

    def test_extract_phone_missing(self):
        self.assertEqual(self.parser._extract_phone("No phone number here."), "")

    def test_extract_name_heuristic(self):
        lines = ["Jane Doe", "jane@example.com", "Summary"]
        name = self.parser._extract_name(lines)
        self.assertEqual(name, "Jane Doe")

    def test_extract_name_skips_email_line(self):
        lines = ["jane@example.com", "Jane Doe Smith"]
        name = self.parser._extract_name(lines)
        self.assertEqual(name, "Jane Doe Smith")

    def test_parse_skills_comma_separated(self):
        lines = ["Python, Go, Kubernetes, Docker, AWS"]
        skills = self.parser._parse_skills(lines)
        self.assertIn("Python", skills)
        self.assertIn("Kubernetes", skills)

    def test_parse_skills_pipe_separated(self):
        lines = ["React | Vue | Angular | TypeScript"]
        skills = self.parser._parse_skills(lines)
        self.assertIn("React", skills)
        self.assertIn("TypeScript", skills)

    def test_parse_certifications(self):
        lines = ["- AWS Certified Solutions Architect", "• CKA"]
        certs = self.parser._parse_certifications(lines)
        self.assertTrue(any("AWS" in c for c in certs))
        self.assertTrue(any("CKA" in c for c in certs))

    def test_parse_summary(self):
        lines = ["Experienced engineer.", "Loves open-source."]
        summary = self.parser._parse_summary(lines)
        self.assertIn("Experienced", summary)
        self.assertIn("open-source", summary)

    def test_segment_sections_experience(self):
        lines = [
            "Jane Doe",
            "Experience",
            "Senior Engineer | Acme | 2020-2023",
            "- Built things",
            "Education",
            "BSc Computer Science 2017",
        ]
        sections = self.parser._segment_sections(lines)
        self.assertIn("experience", sections)
        self.assertIn("education", sections)

    def test_match_section_header_variants(self):
        test_cases = [
            ("Experience", "experience"),
            ("WORK EXPERIENCE", "experience"),
            ("Education", "education"),
            ("Technical Skills", "skills"),
            ("Certifications", "certifications"),
            ("Summary", "summary"),
            ("Professional Summary:", "summary"),
        ]
        for line, expected in test_cases:
            result = self.parser._match_section_header(line)
            self.assertEqual(result, expected, f"Failed for: {line!r}")

    def test_match_section_header_none(self):
        self.assertIsNone(self.parser._match_section_header("Led migration of services"))
        self.assertIsNone(self.parser._match_section_header("2020 – Present"))


class TestResumeMissingFields(unittest.TestCase):
    """Ensure missing fields in resume text result in safe defaults, not crashes."""

    def setUp(self):
        self.parser = ResumeParser()

    @patch("agent.resume_parser.pdfplumber")
    def test_missing_email_defaults_empty(self, mock_pdfplumber):
        text_without_email = "John Smith\nNo contact info.\n\nExperience\n- Did stuff"
        mock_page = MagicMock()
        mock_page.extract_text.return_value = text_without_email
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdfplumber.open.return_value = mock_pdf

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4")
            tmp_path = f.name

        try:
            result = self.parser.parse(tmp_path)
            self.assertEqual(result.get("email", ""), "")
        finally:
            os.unlink(tmp_path)

    @patch("agent.resume_parser.pdfplumber")
    def test_empty_resume_does_not_crash(self, mock_pdfplumber):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdfplumber.open.return_value = mock_pdf

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4")
            tmp_path = f.name

        try:
            # Should not raise
            result = self.parser.parse(tmp_path)
            self.assertIsInstance(result, dict)
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
