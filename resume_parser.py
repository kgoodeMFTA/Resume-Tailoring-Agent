"""
Resume parser supporting PDF and DOCX formats.

Extracts structured data from a candidate's resume, returning a normalised
dict regardless of whether the source file is a PDF or a Word document.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

# PDF parsing
try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore

# DOCX parsing
try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None  # type: ignore


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------
ResumeDict = Dict[str, Any]

# ---------------------------------------------------------------------------
# Regex patterns used for field extraction
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE_RE = re.compile(
    r"(\+?\d{1,3}[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"
)
_SECTION_HEADERS = {
    "summary": re.compile(
        r"^(summary|profile|objective|about me|professional summary)", re.I
    ),
    "experience": re.compile(
        r"^(experience|work experience|employment|professional experience|career history)",
        re.I,
    ),
    "education": re.compile(r"^(education|academic background|qualifications)", re.I),
    "skills": re.compile(
        r"^(skills|technical skills|core competencies|competencies|technologies)",
        re.I,
    ),
    "certifications": re.compile(
        r"^(certifications?|certificates?|accreditations?|licenses?)", re.I
    ),
}


class ResumeParser:
    """
    Parse a resume file (PDF or DOCX) into a structured dictionary.

    Args:
        logger: Optional logger instance; a default one is created if omitted.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, file_path: str) -> ResumeDict:
        """
        Auto-detect format and parse the resume at *file_path*.

        Args:
            file_path: Path to a .pdf or .docx resume file.

        Returns:
            A dict with keys:
              name, email, phone, summary,
              experience (list of dicts), education (list of dicts),
              skills (list of str), certifications (list of str),
              raw_text (str)

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError:        If the file extension is unsupported.
            RuntimeError:      If parsing fails for an unexpected reason.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Resume file not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        self.logger.debug("Parsing resume: %s (extension=%s)", file_path, ext)

        if ext == ".pdf":
            raw_text = self._extract_pdf_text(file_path)
        elif ext in (".docx", ".doc"):
            raw_text = self._extract_docx_text(file_path)
        else:
            raise ValueError(
                f"Unsupported resume format: '{ext}'. "
                "Please provide a .pdf or .docx file."
            )

        self.logger.debug("Extracted %d characters of raw text.", len(raw_text))

        # Attempt structured parse; fall back to lightweight extraction
        try:
            resume = self._structure(raw_text)
        except Exception as exc:  # pragma: no cover
            self.logger.warning(
                "Structured parse failed (%s); falling back to raw extraction.", exc
            )
            resume = self._fallback_structure(raw_text)

        resume["raw_text"] = raw_text
        return resume

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    def _extract_pdf_text(self, file_path: str) -> str:
        """Extract full text from a PDF using pdfplumber."""
        if pdfplumber is None:
            raise RuntimeError(
                "pdfplumber is not installed. Run: pip install pdfplumber"
            )
        pages: List[str] = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n".join(pages)

    def _extract_docx_text(self, file_path: str) -> str:
        """Extract full text from a DOCX using python-docx."""
        if DocxDocument is None:
            raise RuntimeError(
                "python-docx is not installed. Run: pip install python-docx"
            )
        doc = DocxDocument(file_path)
        paragraphs: List[str] = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)

    # ------------------------------------------------------------------
    # Structure detection
    # ------------------------------------------------------------------

    def _structure(self, raw_text: str) -> ResumeDict:
        """
        Parse raw text into a structured resume dict by detecting section
        headers and extracting contact information.
        """
        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

        # ── Contact info ──────────────────────────────────────────────
        name = self._extract_name(lines)
        email = self._extract_email(raw_text)
        phone = self._extract_phone(raw_text)

        # ── Section segmentation ──────────────────────────────────────
        sections = self._segment_sections(lines)

        summary = self._parse_summary(sections.get("summary", []))
        experience = self._parse_experience(sections.get("experience", []))
        education = self._parse_education(sections.get("education", []))
        skills = self._parse_skills(sections.get("skills", []))
        certifications = self._parse_certifications(sections.get("certifications", []))

        return {
            "name": name,
            "email": email,
            "phone": phone,
            "summary": summary,
            "experience": experience,
            "education": education,
            "skills": skills,
            "certifications": certifications,
        }

    def _fallback_structure(self, raw_text: str) -> ResumeDict:
        """Minimal extraction when the structured parser encounters an error."""
        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
        return {
            "name": lines[0] if lines else "Unknown",
            "email": self._extract_email(raw_text),
            "phone": self._extract_phone(raw_text),
            "summary": "",
            "experience": [],
            "education": [],
            "skills": [],
            "certifications": [],
        }

    # ------------------------------------------------------------------
    # Field extractors
    # ------------------------------------------------------------------

    def _extract_name(self, lines: List[str]) -> str:
        """Heuristic: first non-empty line that looks like a name."""
        for line in lines[:5]:
            # Skip lines that are clearly contact info
            if _EMAIL_RE.search(line) or _PHONE_RE.search(line):
                continue
            # A name typically has 2-4 capitalised tokens and no digits
            tokens = line.split()
            if 2 <= len(tokens) <= 5 and not any(ch.isdigit() for ch in line):
                return line
        return lines[0] if lines else "Unknown"

    def _extract_email(self, text: str) -> str:
        match = _EMAIL_RE.search(text)
        return match.group(0) if match else ""

    def _extract_phone(self, text: str) -> str:
        match = _PHONE_RE.search(text)
        return match.group(0).strip() if match else ""

    def _segment_sections(
        self, lines: List[str]
    ) -> Dict[str, List[str]]:
        """
        Split the resume lines into named sections based on header detection.

        Returns a dict mapping section name -> list of content lines.
        """
        sections: Dict[str, List[str]] = {}
        current_section: Optional[str] = None
        current_lines: List[str] = []

        for line in lines:
            matched_section = self._match_section_header(line)
            if matched_section:
                if current_section:
                    sections[current_section] = current_lines
                current_section = matched_section
                current_lines = []
            else:
                current_lines.append(line)

        if current_section:
            sections[current_section] = current_lines

        return sections

    def _match_section_header(self, line: str) -> Optional[str]:
        """Return the canonical section name if *line* is a section header."""
        clean = line.strip().rstrip(":").strip()
        for section_name, pattern in _SECTION_HEADERS.items():
            if pattern.match(clean):
                return section_name
        return None

    # ------------------------------------------------------------------
    # Section parsers
    # ------------------------------------------------------------------

    def _parse_summary(self, lines: List[str]) -> str:
        return " ".join(lines).strip()

    def _parse_skills(self, lines: List[str]) -> List[str]:
        """Extract skills — handles comma-separated, bullet, or line-per-skill."""
        skills: List[str] = []
        for line in lines:
            # Split on common delimiters
            parts = re.split(r"[,|•·\u2022\t]+", line)
            for part in parts:
                cleaned = part.strip().strip("-").strip()
                if cleaned and len(cleaned) < 80:
                    skills.append(cleaned)
        return [s for s in skills if s]

    def _parse_certifications(self, lines: List[str]) -> List[str]:
        certs: List[str] = []
        for line in lines:
            clean = line.strip("-•·* ").strip()
            if clean:
                certs.append(clean)
        return certs

    def _parse_experience(self, lines: List[str]) -> List[Dict[str, Any]]:
        """
        Parse work experience lines into a list of job dicts.

        Each job dict has keys: title, company, dates, bullets.
        """
        jobs: List[Dict[str, Any]] = []
        current_job: Optional[Dict[str, Any]] = None

        date_pattern = re.compile(
            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|present|\d{4})",
            re.I,
        )
        bullet_pattern = re.compile(r"^[\-•·\*\u2022]\s*")

        for line in lines:
            is_bullet = bool(bullet_pattern.match(line))
            has_date = bool(date_pattern.search(line))

            if not is_bullet and has_date and "|" in line:
                # Looks like a job header:  "Title | Company | Dates"
                if current_job:
                    jobs.append(current_job)
                parts = [p.strip() for p in line.split("|")]
                current_job = {
                    "title": parts[0] if len(parts) > 0 else "",
                    "company": parts[1] if len(parts) > 1 else "",
                    "dates": parts[2] if len(parts) > 2 else "",
                    "bullets": [],
                }
            elif not is_bullet and has_date and current_job is None:
                # Job header without pipe separator
                if current_job:
                    jobs.append(current_job)
                current_job = {
                    "title": line,
                    "company": "",
                    "dates": "",
                    "bullets": [],
                }
            elif is_bullet and current_job is not None:
                bullet_text = bullet_pattern.sub("", line).strip()
                if bullet_text:
                    current_job["bullets"].append(bullet_text)
            elif not is_bullet and current_job is not None:
                # Could be company name or continuation line
                if not current_job["company"]:
                    current_job["company"] = line
                elif not current_job["dates"] and has_date:
                    current_job["dates"] = line

        if current_job:
            jobs.append(current_job)

        return jobs

    def _parse_education(self, lines: List[str]) -> List[Dict[str, str]]:
        """
        Parse education lines into a list of dicts with keys:
        degree, institution, dates.
        """
        entries: List[Dict[str, str]] = []
        current: Optional[Dict[str, str]] = None

        date_pattern = re.compile(r"\d{4}")

        for line in lines:
            has_date = bool(date_pattern.search(line))
            if has_date:
                if current:
                    entries.append(current)
                current = {"degree": line, "institution": "", "dates": ""}
                # Extract year(s) from line
                years = date_pattern.findall(line)
                if years:
                    current["dates"] = " – ".join(years)
            elif current and not current["institution"]:
                current["institution"] = line
            elif current:
                # Additional detail lines appended to degree
                current["degree"] += f", {line}"

        if current:
            entries.append(current)

        return entries
