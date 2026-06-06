"""
Job posting scraper.

Fetches and parses job postings from any URL, with special handling for
common job boards (LinkedIn, Indeed, Greenhouse, Lever, Workday).
Uses ``requests`` for HTTP, ``BeautifulSoup4`` for HTML, and
``readability-lxml`` for main-content extraction.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from readability import Document as ReadabilityDocument
except ImportError:
    ReadabilityDocument = None  # type: ignore

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------
JobDict = Dict[str, Any]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_REQUEST_TIMEOUT = 15  # seconds

# ---------------------------------------------------------------------------
# Board-specific selectors
# ---------------------------------------------------------------------------
_BOARD_SELECTORS: Dict[str, Dict[str, str]] = {
    "linkedin.com": {
        "title": "h1.top-card-layout__title",
        "company": "a.topcard__org-name-link",
        "location": "span.topcard__flavor--bullet",
        "description": "div.description__text",
    },
    "indeed.com": {
        "title": "h1.jobsearch-JobInfoHeader-title",
        "company": "div[data-company-name='true']",
        "location": "div#jobDetailsSection",
        "description": "div#jobDescriptionText",
    },
    "greenhouse.io": {
        "title": "h1.app-title",
        "company": "h2.company-name",
        "location": "div.location",
        "description": "div#content",
    },
    "lever.co": {
        "title": "h2",
        "company": "a.main-header-logo",
        "location": "div.posting-categories",
        "description": "div.section-wrapper",
    },
    "myworkdayjobs.com": {
        "title": "h2[data-automation-id='jobPostingHeader']",
        "company": "a.css-1q2dra3",
        "location": "div[data-automation-id='locations']",
        "description": "div[data-automation-id='jobPostingDescription']",
    },
}


class JobScraper:
    """
    Fetch and parse a job posting from any URL.

    Attempts board-specific extraction first (LinkedIn, Indeed, Greenhouse,
    Lever, Workday), then falls back to readability-lxml article extraction,
    and finally to plain BeautifulSoup text extraction.

    Args:
        logger:  Optional logger; a default one is created if omitted.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        timeout: int = _REQUEST_TIMEOUT,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(_DEFAULT_HEADERS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape(self, url: str) -> JobDict:
        """
        Fetch and parse the job posting at *url*.

        Args:
            url: Full HTTP/HTTPS URL of the job posting.

        Returns:
            A dict with keys:
              title, company, location, description, requirements,
              preferred_qualifications, raw_text

        Raises:
            ValueError:   If the URL scheme is not HTTP/HTTPS.
            RuntimeError: If the HTTP request fails or returns a non-200 status.
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: '{parsed.scheme}'")

        self.logger.debug("Fetching job posting: %s", url)
        html = self._fetch_html(url)
        self.logger.debug("Fetched %d bytes of HTML.", len(html))

        # Detect which board (if any) we're dealing with
        domain = parsed.netloc.lower()
        board_key = self._detect_board(domain)

        if board_key:
            self.logger.debug("Detected board: %s", board_key)
            job = self._parse_board(html, board_key)
        else:
            self.logger.debug("Using generic parser.")
            job = self._parse_generic(html)

        # Ensure all expected fields are present
        job = self._normalise(job)

        # Split description into requirements / preferred
        job = self._split_requirements(job)

        self.logger.info(
            "Scraped job: '%s' at '%s'", job.get("title"), job.get("company")
        )
        return job

    # ------------------------------------------------------------------
    # HTTP layer
    # ------------------------------------------------------------------

    def _fetch_html(self, url: str) -> str:
        """Perform the GET request and return response HTML text."""
        try:
            response = self._session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(
                f"HTTP {exc.response.status_code} error fetching {url}: {exc}"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(f"Connection error fetching {url}: {exc}") from exc
        except requests.exceptions.Timeout:
            raise RuntimeError(
                f"Request timed out after {self.timeout}s for {url}"
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Request failed for {url}: {exc}") from exc

    # ------------------------------------------------------------------
    # Board-specific parsers
    # ------------------------------------------------------------------

    def _detect_board(self, domain: str) -> Optional[str]:
        """Return the matching board key if the domain is a known job board."""
        for board_domain in _BOARD_SELECTORS:
            if board_domain in domain:
                return board_domain
        return None

    def _parse_board(self, html: str, board_key: str) -> JobDict:
        """Extract fields using board-specific CSS selectors."""
        soup = BeautifulSoup(html, "lxml")
        selectors = _BOARD_SELECTORS[board_key]

        def _get(selector: str) -> str:
            el = soup.select_one(selector)
            return el.get_text(separator=" ", strip=True) if el else ""

        return {
            "title": _get(selectors.get("title", "")),
            "company": _get(selectors.get("company", "")),
            "location": _get(selectors.get("location", "")),
            "description": _get(selectors.get("description", "")),
            "raw_text": soup.get_text(separator="\n", strip=True),
        }

    # ------------------------------------------------------------------
    # Generic parser
    # ------------------------------------------------------------------

    def _parse_generic(self, html: str) -> JobDict:
        """
        Extract job content using readability-lxml (if available) or
        falling back to BeautifulSoup heuristics.
        """
        if ReadabilityDocument is not None:
            doc = ReadabilityDocument(html)
            article_html = doc.summary()
            title = doc.short_title()
            soup = BeautifulSoup(article_html, "lxml")
            description = soup.get_text(separator="\n", strip=True)
        else:
            soup = BeautifulSoup(html, "lxml")
            title = self._extract_title(soup)
            description = self._extract_main_content(soup)

        raw_soup = BeautifulSoup(html, "lxml")
        return {
            "title": title,
            "company": self._extract_company(raw_soup),
            "location": self._extract_location(raw_soup),
            "description": description,
            "raw_text": raw_soup.get_text(separator="\n", strip=True),
        }

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Try common title patterns."""
        for selector in ("h1", "title", "h2"):
            el = soup.find(selector)
            if el:
                return el.get_text(strip=True)
        return ""

    def _extract_company(self, soup: BeautifulSoup) -> str:
        """Heuristic company extraction from meta tags and common elements."""
        # og:site_name often holds the company / site name
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            return og_site["content"].strip()

        # Try schema.org hiringOrganization
        el = soup.find(itemprop="hiringOrganization")
        if el:
            name_el = el.find(itemprop="name")
            if name_el:
                return name_el.get_text(strip=True)

        return ""

    def _extract_location(self, soup: BeautifulSoup) -> str:
        """Heuristic location extraction from schema.org and common classes."""
        el = soup.find(itemprop="jobLocation")
        if el:
            return el.get_text(separator=", ", strip=True)
        for cls in ("location", "job-location", "posting-location"):
            el = soup.find(class_=cls)
            if el:
                return el.get_text(strip=True)
        return ""

    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """
        Strip navigation, headers, and footers; return likely main content.
        """
        # Remove noisy elements
        for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
            tag.decompose()

        # Try common content containers
        for selector in (
            "article",
            "main",
            "div[class*='description']",
            "div[class*='content']",
            "div[id*='description']",
            "div[id*='content']",
        ):
            el = soup.select_one(selector)
            if el and len(el.get_text(strip=True)) > 200:
                return el.get_text(separator="\n", strip=True)

        return soup.get_text(separator="\n", strip=True)

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def _normalise(self, job: JobDict) -> JobDict:
        """Ensure every expected key exists with at least an empty value."""
        defaults: JobDict = {
            "title": "",
            "company": "",
            "location": "",
            "description": "",
            "requirements": "",
            "preferred_qualifications": "",
            "raw_text": "",
        }
        return {**defaults, **job}

    def _split_requirements(self, job: JobDict) -> JobDict:
        """
        Heuristically split *description* into hard requirements and
        preferred qualifications sections.
        """
        description = job.get("description", "")
        if not description:
            return job

        pref_pattern = re.compile(
            r"(preferred qualifications?|nice[- ]to[- ]have|bonus|pluses?|desired|"
            r"^preferred$)",
            re.I,
        )
        req_pattern = re.compile(
            r"(^requirements?$|what you.ll need|must[- ]have|"
            r"minimum qualifications?|basic qualifications?|"
            r"^qualifications?$)",
            re.I,
        )

        lines = description.splitlines()
        mode = "description"
        req_lines: List[str] = []
        pref_lines: List[str] = []
        desc_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if pref_pattern.search(stripped):
                mode = "preferred"
            elif req_pattern.search(stripped):
                mode = "requirements"

            if mode == "requirements":
                req_lines.append(line)
            elif mode == "preferred":
                pref_lines.append(line)
            else:
                desc_lines.append(line)

        job["description"] = "\n".join(desc_lines).strip() or description
        job["requirements"] = "\n".join(req_lines).strip()
        job["preferred_qualifications"] = "\n".join(pref_lines).strip()
        return job
