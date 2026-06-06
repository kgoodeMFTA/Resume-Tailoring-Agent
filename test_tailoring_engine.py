"""
Unit tests for agent.tailoring_engine.TailoringEngine.

Tests cover:
  - Prompt template rendering (no LLM call needed)
  - JSON response parsing (valid, markdown-fenced, malformed)
  - Mock OpenAI calls: successful tailor(), analysis stage, tailoring stage
  - _changes key is always present in output
  - RuntimeError raised on API failure
  - Truncation helper
  - raw_text preservation through tailoring
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.tailoring_engine import TailoringEngine

# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESUME = {
    "name": "Alex Kim",
    "email": "alex@example.com",
    "phone": "+1 555-999-0000",
    "summary": "Software engineer with 6 years of experience building web services.",
    "experience": [
        {
            "title": "Software Engineer",
            "company": "BigCorp",
            "dates": "Jan 2019 – Present",
            "bullets": [
                "Built REST APIs using Django",
                "Maintained PostgreSQL databases",
                "Participated in code reviews",
            ],
        }
    ],
    "education": [
        {
            "degree": "BSc Computer Science",
            "institution": "State University",
            "dates": "2015 – 2019",
        }
    ],
    "skills": ["Python", "Django", "PostgreSQL", "Docker"],
    "certifications": [],
    "raw_text": "Alex Kim\nalex@example.com\n+1 555-999-0000\n...",
}

SAMPLE_JOB = {
    "title": "Senior Backend Engineer",
    "company": "StartupAI",
    "location": "Remote",
    "description": "We are looking for a senior backend engineer to join our platform team.",
    "requirements": "5+ years Python, experience with microservices, Kubernetes",
    "preferred_qualifications": "Experience with ML pipelines",
    "raw_text": "...",
}

SAMPLE_ANALYSIS = {
    "must_have_skills": ["Python", "Kubernetes", "Microservices"],
    "nice_to_have_skills": ["ML pipelines", "Rust"],
    "core_responsibilities": [
        "Design and maintain microservices",
        "Own deployment pipelines",
        "Collaborate with ML teams",
    ],
    "ats_keywords": [
        "microservices", "Kubernetes", "distributed systems",
        "Python", "backend", "API", "REST", "CI/CD", "Docker",
    ],
    "seniority_level": "senior",
    "role_type": "backend engineer",
    "industry_context": "AI startup building developer tools",
    "culture_keywords": ["ownership", "autonomy", "impact", "fast-paced"],
}

SAMPLE_TAILORED_RESUME = {
    **SAMPLE_RESUME,
    "summary": "Senior backend engineer with 6 years building scalable microservices and REST APIs.",
    "skills": ["Python", "Django", "PostgreSQL", "Docker", "Kubernetes", "Microservices"],
    "_changes": [
        "Updated summary to highlight microservices experience",
        "Added Kubernetes to skills list",
        "Reordered experience bullets for relevance",
    ],
}


def _make_openai_response(content: str) -> MagicMock:
    """Build a mock OpenAI ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


class TestTailoringEngineInit(unittest.TestCase):
    def test_init_stores_model_and_tokens(self):
        engine = TailoringEngine(
            openai_api_key="sk-test",
            model_name="gpt-4o",
            max_tokens=2000,
        )
        self.assertEqual(engine.model_name, "gpt-4o")
        self.assertEqual(engine.max_tokens, 2000)

    def test_init_creates_openai_client(self):
        engine = TailoringEngine(openai_api_key="sk-test")
        self.assertIsNotNone(engine._client)


class TestJSONParsing(unittest.TestCase):
    def setUp(self):
        self.engine = TailoringEngine(openai_api_key="sk-test")

    def test_parse_clean_json(self):
        data = {"key": "value", "list": [1, 2, 3]}
        text = json.dumps(data)
        result = self.engine._parse_json_response(text, stage="test")
        self.assertEqual(result, data)

    def test_parse_markdown_fenced_json(self):
        data = {"name": "test", "value": 42}
        text = f"```json\n{json.dumps(data)}\n```"
        result = self.engine._parse_json_response(text, stage="test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 42)

    def test_parse_markdown_fenced_no_lang(self):
        data = {"foo": "bar"}
        text = f"```\n{json.dumps(data)}\n```"
        result = self.engine._parse_json_response(text, stage="test")
        self.assertEqual(result, data)

    def test_parse_malformed_raises(self):
        with self.assertRaises(RuntimeError) as ctx:
            self.engine._parse_json_response(
                "This is definitely not JSON at all", stage="test_stage"
            )
        self.assertIn("test_stage", str(ctx.exception))

    def test_parse_empty_raises(self):
        with self.assertRaises(RuntimeError):
            self.engine._parse_json_response("", stage="empty")


class TestTruncation(unittest.TestCase):
    def setUp(self):
        self.engine = TailoringEngine(openai_api_key="sk-test")

    def test_short_text_unchanged(self):
        text = "Hello world"
        self.assertEqual(self.engine._truncate(text, 100), text)

    def test_long_text_truncated(self):
        text = "A" * 500
        result = self.engine._truncate(text, 100)
        self.assertLessEqual(len(result), 120)  # 100 + ellipsis
        self.assertIn("truncated", result)

    def test_exact_length_unchanged(self):
        text = "B" * 50
        result = self.engine._truncate(text, 50)
        self.assertEqual(result, text)


class TestPromptRendering(unittest.TestCase):
    """Verify prompts render correctly without making any API calls."""

    def setUp(self):
        self.engine = TailoringEngine(openai_api_key="sk-test")

    def test_analysis_prompt_contains_job_title(self):
        prompt = self.engine.get_analysis_prompt(SAMPLE_JOB)
        self.assertIn("Senior Backend Engineer", prompt)

    def test_analysis_prompt_contains_company(self):
        prompt = self.engine.get_analysis_prompt(SAMPLE_JOB)
        self.assertIn("StartupAI", prompt)

    def test_analysis_prompt_contains_requirements(self):
        prompt = self.engine.get_analysis_prompt(SAMPLE_JOB)
        self.assertIn("Kubernetes", prompt)

    def test_tailoring_prompt_contains_resume_json(self):
        prompt = self.engine.get_tailoring_prompt(
            SAMPLE_RESUME, SAMPLE_JOB, SAMPLE_ANALYSIS
        )
        self.assertIn("Alex Kim", prompt)

    def test_tailoring_prompt_contains_seniority(self):
        prompt = self.engine.get_tailoring_prompt(
            SAMPLE_RESUME, SAMPLE_JOB, SAMPLE_ANALYSIS
        )
        self.assertIn("senior", prompt)

    def test_tailoring_prompt_excludes_raw_text(self):
        """raw_text should be stripped from the resume JSON in the prompt."""
        prompt = self.engine.get_tailoring_prompt(
            SAMPLE_RESUME, SAMPLE_JOB, SAMPLE_ANALYSIS
        )
        # The raw_text value itself contains a unique marker
        self.assertNotIn("alex@example.com\n+1 555", prompt)


class TestAnalyseJob(unittest.TestCase):
    """Test the _analyse_job stage with mocked OpenAI."""

    def setUp(self):
        self.engine = TailoringEngine(openai_api_key="sk-test")

    def test_analyse_job_returns_dict(self):
        mock_resp = _make_openai_response(json.dumps(SAMPLE_ANALYSIS))
        with patch.object(
            self.engine._client.chat.completions, "create", return_value=mock_resp
        ):
            result = self.engine._analyse_job(SAMPLE_JOB)
        self.assertIsInstance(result, dict)
        self.assertIn("must_have_skills", result)

    def test_analyse_job_api_error_raises(self):
        with patch.object(
            self.engine._client.chat.completions, "create",
            side_effect=Exception("API down"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                self.engine._analyse_job(SAMPLE_JOB)
            self.assertIn("OpenAI API", str(ctx.exception))


class TestTailorResume(unittest.TestCase):
    """Test the _tailor_resume stage with mocked OpenAI."""

    def setUp(self):
        self.engine = TailoringEngine(openai_api_key="sk-test")

    def test_tailor_returns_resume_dict(self):
        mock_resp = _make_openai_response(json.dumps(SAMPLE_TAILORED_RESUME))
        with patch.object(
            self.engine._client.chat.completions, "create", return_value=mock_resp
        ):
            result = self.engine._tailor_resume(
                SAMPLE_RESUME, SAMPLE_JOB, SAMPLE_ANALYSIS
            )
        self.assertIsInstance(result, dict)
        self.assertIn("name", result)

    def test_tailor_preserves_raw_text(self):
        mock_resp = _make_openai_response(json.dumps(SAMPLE_TAILORED_RESUME))
        with patch.object(
            self.engine._client.chat.completions, "create", return_value=mock_resp
        ):
            result = self.engine._tailor_resume(
                SAMPLE_RESUME, SAMPLE_JOB, SAMPLE_ANALYSIS
            )
        # raw_text from original resume should be preserved
        self.assertEqual(result.get("raw_text"), SAMPLE_RESUME["raw_text"])

    def test_tailor_changes_key_present(self):
        tailored_without_changes = {**SAMPLE_TAILORED_RESUME}
        del tailored_without_changes["_changes"]
        mock_resp = _make_openai_response(json.dumps(tailored_without_changes))
        with patch.object(
            self.engine._client.chat.completions, "create", return_value=mock_resp
        ):
            result = self.engine._tailor_resume(
                SAMPLE_RESUME, SAMPLE_JOB, SAMPLE_ANALYSIS
            )
        # _changes should default to empty list if not returned by model
        self.assertIn("_changes", result)
        self.assertIsInstance(result["_changes"], list)


class TestTailorFullPipeline(unittest.TestCase):
    """Test the public tailor() method (two-stage pipeline)."""

    def setUp(self):
        self.engine = TailoringEngine(openai_api_key="sk-test")

    def test_tailor_calls_both_stages(self):
        analysis_resp = _make_openai_response(json.dumps(SAMPLE_ANALYSIS))
        tailored_resp = _make_openai_response(json.dumps(SAMPLE_TAILORED_RESUME))

        with patch.object(
            self.engine._client.chat.completions, "create",
            side_effect=[analysis_resp, tailored_resp],
        ):
            result = self.engine.tailor(SAMPLE_RESUME, SAMPLE_JOB)

        self.assertIsInstance(result, dict)
        self.assertIn("name", result)
        self.assertIn("_changes", result)

    def test_tailor_returns_changes_list(self):
        analysis_resp = _make_openai_response(json.dumps(SAMPLE_ANALYSIS))
        tailored_resp = _make_openai_response(json.dumps(SAMPLE_TAILORED_RESUME))

        with patch.object(
            self.engine._client.chat.completions, "create",
            side_effect=[analysis_resp, tailored_resp],
        ):
            result = self.engine.tailor(SAMPLE_RESUME, SAMPLE_JOB)

        self.assertIsInstance(result["_changes"], list)
        self.assertGreater(len(result["_changes"]), 0)

    def test_tailor_analysis_failure_raises_runtime(self):
        with patch.object(
            self.engine._client.chat.completions, "create",
            side_effect=Exception("Network error"),
        ):
            with self.assertRaises(RuntimeError):
                self.engine.tailor(SAMPLE_RESUME, SAMPLE_JOB)

    def test_tailor_malformed_analysis_raises_runtime(self):
        bad_resp = _make_openai_response("not valid json at all ##!!")
        with patch.object(
            self.engine._client.chat.completions, "create",
            return_value=bad_resp,
        ):
            with self.assertRaises(RuntimeError):
                self.engine.tailor(SAMPLE_RESUME, SAMPLE_JOB)

    def test_tailor_malformed_tailoring_raises_runtime(self):
        good_analysis = _make_openai_response(json.dumps(SAMPLE_ANALYSIS))
        bad_tailoring = _make_openai_response("{{definitely not json")
        with patch.object(
            self.engine._client.chat.completions, "create",
            side_effect=[good_analysis, bad_tailoring],
        ):
            with self.assertRaises(RuntimeError):
                self.engine.tailor(SAMPLE_RESUME, SAMPLE_JOB)


class TestSystemPromptConstants(unittest.TestCase):
    """Sanity-check that prompt constants contain key instructional phrases."""

    def test_analysis_system_prompt_mentions_ats(self):
        self.assertIn("ATS", TailoringEngine.ANALYSIS_SYSTEM_PROMPT)

    def test_tailoring_system_prompt_no_fabrication_rule(self):
        self.assertIn("NEVER fabricate", TailoringEngine.TAILORING_SYSTEM_PROMPT)

    def test_tailoring_system_prompt_mentions_action_verbs(self):
        self.assertIn("action verbs", TailoringEngine.TAILORING_SYSTEM_PROMPT)

    def test_tailoring_system_prompt_mentions_json(self):
        self.assertIn("JSON", TailoringEngine.TAILORING_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
