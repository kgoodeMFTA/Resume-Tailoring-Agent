"""
Unit tests for agent.job_scraper.JobScraper.

Tests cover:
  - URL scheme validation
  - Successful scrape with mocked HTTP response
  - HTTP error handling (4xx, 5xx)
  - Connection error handling
  - Board detection (LinkedIn, Greenhouse, Lever, Indeed, Workday)
  - Generic article extraction fallback
  - Requirements section splitting
  - Field normalisation (all keys present)
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.job_scraper import JobScraper

# ---------------------------------------------------------------------------
# Sample HTML fixtures
# ---------------------------------------------------------------------------

SAMPLE_GREENHOUSE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Senior Python Engineer | Acme Corp</title></head>
<body>
  <h1 class="app-title">Senior Python Engineer</h1>
  <h2 class="company-name">Acme Corp</h2>
  <div class="location">San Francisco, CA (Remote OK)</div>
  <div id="content">
    <p>We are looking for a Senior Python Engineer to join our platform team.</p>
    <h3>Requirements</h3>
    <ul>
      <li>5+ years of Python experience</li>
      <li>Experience with distributed systems</li>
      <li>Strong SQL skills</li>
    </ul>
    <h3>Preferred Qualifications</h3>
    <ul>
      <li>Experience with Kubernetes</li>
      <li>Open-source contributions</li>
    </ul>
  </div>
</body>
</html>
"""

SAMPLE_GENERIC_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Data Scientist — TechCo</title>
  <meta property="og:site_name" content="TechCo Careers">
</head>
<body>
  <nav>Navigation garbage</nav>
  <main>
    <h1>Data Scientist</h1>
    <article>
      <p>TechCo is hiring a Data Scientist to work on ML pipelines.</p>
      <p>Requirements: 3 years ML experience, Python, TensorFlow.</p>
      <p>Preferred: PhD in Statistics, experience with LLMs.</p>
    </article>
  </main>
  <footer>Footer garbage</footer>
</body>
</html>
"""

SAMPLE_MINIMAL_HTML = """
<html><body><h1>Software Engineer</h1><p>Build cool things.</p></body></html>
"""


def _make_mock_response(html: str, status_code: int = 200) -> MagicMock:
    """Helper to create a mock requests.Response."""
    response = MagicMock()
    response.status_code = status_code
    response.text = html
    if status_code >= 400:
        import requests
        http_error = requests.exceptions.HTTPError(response=response)
        response.raise_for_status.side_effect = http_error
    else:
        response.raise_for_status.return_value = None
    return response


class TestJobScraperInit(unittest.TestCase):
    def test_default_init(self):
        scraper = JobScraper()
        self.assertIsNotNone(scraper.logger)
        self.assertEqual(scraper.timeout, 15)

    def test_custom_timeout(self):
        scraper = JobScraper(timeout=30)
        self.assertEqual(scraper.timeout, 30)


class TestURLValidation(unittest.TestCase):
    def setUp(self):
        self.scraper = JobScraper()

    def test_invalid_scheme_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self.scraper.scrape("ftp://example.com/job")
        self.assertIn("scheme", str(ctx.exception).lower())

    def test_file_scheme_raises(self):
        with self.assertRaises(ValueError):
            self.scraper.scrape("file:///etc/passwd")

    def test_no_scheme_raises(self):
        with self.assertRaises(ValueError):
            self.scraper.scrape("example.com/job")


class TestHTTPErrors(unittest.TestCase):
    def setUp(self):
        self.scraper = JobScraper()

    @patch("agent.job_scraper.requests.Session.get")
    def test_404_raises_runtime_error(self, mock_get):
        mock_get.return_value = _make_mock_response("Not Found", 404)
        with self.assertRaises(RuntimeError) as ctx:
            self.scraper.scrape("https://example.com/job/missing")
        self.assertIn("404", str(ctx.exception))

    @patch("agent.job_scraper.requests.Session.get")
    def test_500_raises_runtime_error(self, mock_get):
        mock_get.return_value = _make_mock_response("Server Error", 500)
        with self.assertRaises(RuntimeError):
            self.scraper.scrape("https://example.com/job/broken")

    @patch("agent.job_scraper.requests.Session.get")
    def test_connection_error_raises(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("timeout")
        with self.assertRaises(RuntimeError) as ctx:
            self.scraper.scrape("https://unreachable.example.com/job")
        self.assertIn("Connection error", str(ctx.exception))

    @patch("agent.job_scraper.requests.Session.get")
    def test_timeout_raises(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()
        with self.assertRaises(RuntimeError) as ctx:
            self.scraper.scrape("https://slow.example.com/job")
        self.assertIn("timed out", str(ctx.exception))


class TestBoardDetection(unittest.TestCase):
    def setUp(self):
        self.scraper = JobScraper()

    def test_detects_greenhouse(self):
        result = self.scraper._detect_board("boards.greenhouse.io")
        self.assertEqual(result, "greenhouse.io")

    def test_detects_lever(self):
        result = self.scraper._detect_board("jobs.lever.co")
        self.assertEqual(result, "lever.co")

    def test_detects_linkedin(self):
        result = self.scraper._detect_board("www.linkedin.com")
        self.assertEqual(result, "linkedin.com")

    def test_detects_indeed(self):
        result = self.scraper._detect_board("www.indeed.com")
        self.assertEqual(result, "indeed.com")

    def test_detects_workday(self):
        result = self.scraper._detect_board("company.myworkdayjobs.com")
        self.assertEqual(result, "myworkdayjobs.com")

    def test_unknown_domain_returns_none(self):
        result = self.scraper._detect_board("careers.randomcompany.com")
        self.assertIsNone(result)


class TestGreenhouseParse(unittest.TestCase):
    def setUp(self):
        self.scraper = JobScraper()

    @patch("agent.job_scraper.requests.Session.get")
    def test_greenhouse_scrape_returns_dict(self, mock_get):
        mock_get.return_value = _make_mock_response(SAMPLE_GREENHOUSE_HTML)
        result = self.scraper.scrape("https://boards.greenhouse.io/acme/jobs/12345")
        self._assert_job_keys(result)

    @patch("agent.job_scraper.requests.Session.get")
    def test_greenhouse_title_extracted(self, mock_get):
        mock_get.return_value = _make_mock_response(SAMPLE_GREENHOUSE_HTML)
        result = self.scraper.scrape("https://boards.greenhouse.io/acme/jobs/12345")
        self.assertIn("Python Engineer", result["title"])

    @patch("agent.job_scraper.requests.Session.get")
    def test_greenhouse_company_extracted(self, mock_get):
        mock_get.return_value = _make_mock_response(SAMPLE_GREENHOUSE_HTML)
        result = self.scraper.scrape("https://boards.greenhouse.io/acme/jobs/12345")
        self.assertIn("Acme", result["company"])

    def _assert_job_keys(self, job: dict):
        expected = [
            "title", "company", "location", "description",
            "requirements", "preferred_qualifications", "raw_text"
        ]
        for key in expected:
            self.assertIn(key, job, f"Missing key: {key}")


class TestGenericParse(unittest.TestCase):
    def setUp(self):
        self.scraper = JobScraper()

    @patch("agent.job_scraper.requests.Session.get")
    def test_generic_scrape_has_all_keys(self, mock_get):
        mock_get.return_value = _make_mock_response(SAMPLE_GENERIC_HTML)
        result = self.scraper.scrape("https://careers.techco.com/data-scientist")
        expected_keys = [
            "title", "company", "location", "description",
            "requirements", "preferred_qualifications", "raw_text"
        ]
        for key in expected_keys:
            self.assertIn(key, result)

    @patch("agent.job_scraper.requests.Session.get")
    def test_generic_company_from_og_meta(self, mock_get):
        mock_get.return_value = _make_mock_response(SAMPLE_GENERIC_HTML)
        result = self.scraper.scrape("https://careers.techco.com/data-scientist")
        self.assertIn("TechCo", result["company"])

    @patch("agent.job_scraper.requests.Session.get")
    def test_minimal_html_does_not_crash(self, mock_get):
        mock_get.return_value = _make_mock_response(SAMPLE_MINIMAL_HTML)
        result = self.scraper.scrape("https://example.com/job")
        self.assertIsInstance(result, dict)


class TestNormalisationAndSplitting(unittest.TestCase):
    def setUp(self):
        self.scraper = JobScraper()

    def test_normalise_fills_missing_keys(self):
        partial = {"title": "Engineer"}
        normalised = self.scraper._normalise(partial)
        for key in ["company", "location", "description", "requirements",
                    "preferred_qualifications", "raw_text"]:
            self.assertIn(key, normalised)
            self.assertEqual(normalised[key], "")
        self.assertEqual(normalised["title"], "Engineer")

    def test_split_requirements_separates_sections(self):
        job = {
            "description": (
                "We are building the future.\n\n"
                "Requirements\n"
                "- 5 years Python\n"
                "- Strong algorithms\n"
                "Preferred Qualifications\n"
                "- Experience with LLMs\n"
            ),
            "requirements": "",
            "preferred_qualifications": "",
            "title": "", "company": "", "location": "", "raw_text": "",
        }
        result = self.scraper._split_requirements(job)
        self.assertIn("Python", result["requirements"])
        self.assertIn("LLMs", result["preferred_qualifications"])

    def test_split_requirements_empty_description_unchanged(self):
        job = {
            "title": "SWE", "company": "", "location": "",
            "description": "", "requirements": "", "preferred_qualifications": "",
            "raw_text": "",
        }
        result = self.scraper._split_requirements(job)
        self.assertEqual(result["requirements"], "")
        self.assertEqual(result["preferred_qualifications"], "")


class TestScraperHelpers(unittest.TestCase):
    def setUp(self):
        self.scraper = JobScraper()

    def test_extract_title_from_h1(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<html><body><h1>Machine Learning Engineer</h1></body></html>", "lxml")
        title = self.scraper._extract_title(soup)
        self.assertEqual(title, "Machine Learning Engineer")

    def test_extract_location_from_itemprop(self):
        from bs4 import BeautifulSoup
        html = '<span itemprop="jobLocation"><span itemprop="name">New York, NY</span></span>'
        soup = BeautifulSoup(html, "lxml")
        location = self.scraper._extract_location(soup)
        self.assertIn("New York", location)

    def test_extract_main_content_removes_nav(self):
        from bs4 import BeautifulSoup
        html = (
            "<html><body>"
            "<nav>Top nav garbage ×100 " + "word " * 50 + "</nav>"
            "<main><p>" + "Main content. " * 30 + "</p></main>"
            "<footer>Footer garbage</footer>"
            "</body></html>"
        )
        soup = BeautifulSoup(html, "lxml")
        content = self.scraper._extract_main_content(soup)
        self.assertNotIn("Top nav", content)
        self.assertIn("Main content", content)


if __name__ == "__main__":
    unittest.main()
