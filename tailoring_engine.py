"""
AI tailoring engine powered by OpenAI GPT-4o.

Uses a two-stage prompting strategy:
  1. **Analysis** — extract key skills, keywords, and requirements from the
     job posting.
  2. **Tailoring** — rewrite and optimise the resume to align with those
     requirements without fabricating experience.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------
ResumeDict = Dict[str, Any]
JobDict = Dict[str, Any]


class TailoringEngine:
    """
    Tailor a parsed resume dict to a specific job posting using GPT-4o.

    The engine runs two LLM calls:

    1. **Job Analysis** — Summarises what the employer is actually looking
       for (must-have skills, nice-to-have skills, core responsibilities,
       culture keywords).
    2. **Resume Tailoring** — Rewrites the resume summary, reorders and
       enhances bullet points, adds missing ATS keywords, and aligns the
       skills section, all while preserving factual accuracy.

    Args:
        openai_api_key: API key for the OpenAI service.
        model_name:     Model identifier (default: ``gpt-4o``).
        max_tokens:     Maximum tokens per completion call.
        logger:         Optional logger instance.
    """

    # ------------------------------------------------------------------
    # Prompt templates (class-level constants for easy customisation)
    # ------------------------------------------------------------------

    ANALYSIS_SYSTEM_PROMPT = """You are an expert technical recruiter and career coach.
Your task is to analyse a job posting and extract structured information that will help
tailor a candidate's resume for maximum ATS (Applicant Tracking System) compatibility
and human reviewer impact.

Return ONLY valid JSON. Do not include any explanation outside the JSON block."""

    ANALYSIS_USER_PROMPT = """Analyse the following job posting and extract:

1. must_have_skills: A list of skills/technologies explicitly required.
2. nice_to_have_skills: A list of preferred or bonus skills.
3. core_responsibilities: Top 5 responsibilities in the role.
4. ats_keywords: 15-20 specific keywords and phrases to include in the resume.
5. seniority_level: One of [entry, mid, senior, lead, staff, principal, executive].
6. role_type: e.g., "software engineer", "data scientist", "product manager", etc.
7. industry_context: Short description of the company/industry context.
8. culture_keywords: 3-5 values or cultural signals from the posting.

Job Title: {title}
Company: {company}
Location: {location}

Job Description:
{description}

Requirements:
{requirements}

Preferred Qualifications:
{preferred_qualifications}

Respond with a JSON object containing the 8 keys listed above."""

    TAILORING_SYSTEM_PROMPT = """You are an expert resume writer and career coach specialising in
ATS optimisation and executive-level resume tailoring. You help candidates present their authentic
experience in the most compelling way possible for specific roles.

CRITICAL RULES — follow these without exception:
1. NEVER fabricate, invent, or exaggerate experience, titles, dates, or achievements.
2. ALWAYS use strong action verbs (Led, Designed, Built, Delivered, Reduced, Increased, etc.).
3. Quantify achievements wherever the original text provides enough context (%, $, x).
4. Add ATS keywords naturally — they must read as genuine descriptions of real work.
5. Reorder experience bullets to highlight the most relevant achievements first.
6. Keep the professional tone consistent with the target seniority level.
7. Return ONLY valid JSON matching the input resume schema exactly.
8. Add a "_changes" key listing (max 10) specific changes made as short strings."""

    TAILORING_USER_PROMPT = """You are tailoring a resume for the following job:

TARGET ROLE: {title} at {company}
SENIORITY: {seniority_level}
ROLE TYPE: {role_type}

JOB ANALYSIS:
{job_analysis}

CURRENT RESUME:
{resume_json}

Your task:
1. Rewrite the "summary" to directly address this role's requirements (3-4 sentences max).
2. For each job in "experience", reorder bullets to front-load the most relevant achievements
   and enhance language to include ATS keywords naturally.
3. Ensure the "skills" list includes all must_have_skills that the candidate demonstrably has.
4. Improve "certifications" ordering if relevant certifications are listed.
5. Add a "_changes" key with a list of specific improvements made (max 10 items).

Return the complete updated resume as valid JSON, preserving all original fields.
Do NOT add, remove, or alter any job title, company name, date, or education entry."""

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        openai_api_key: str,
        model_name: str = "gpt-4o",
        max_tokens: int = 4000,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.logger = logger or logging.getLogger(__name__)
        self._client = OpenAI(api_key=openai_api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tailor(self, resume: ResumeDict, job: JobDict) -> ResumeDict:
        """
        Run the two-stage tailoring pipeline.

        Args:
            resume: Structured resume dict from :class:`ResumeParser`.
            job:    Structured job dict from :class:`JobScraper`.

        Returns:
            Updated resume dict with tailored content plus a ``_changes``
            key listing what was modified.

        Raises:
            RuntimeError: If either LLM call fails or returns malformed JSON.
        """
        self.logger.info("Stage 1/2: Analysing job posting …")
        job_analysis = self._analyse_job(job)
        self.logger.debug("Job analysis: %s", json.dumps(job_analysis, indent=2))

        self.logger.info("Stage 2/2: Tailoring resume …")
        tailored = self._tailor_resume(resume, job, job_analysis)
        self.logger.debug("Tailoring changes: %s", tailored.get("_changes", []))

        return tailored

    # ------------------------------------------------------------------
    # Stage 1: Job analysis
    # ------------------------------------------------------------------

    def _analyse_job(self, job: JobDict) -> Dict[str, Any]:
        """
        Call GPT to extract structured requirements from the job posting.

        Returns:
            Dict with keys: must_have_skills, nice_to_have_skills,
            core_responsibilities, ats_keywords, seniority_level,
            role_type, industry_context, culture_keywords.
        """
        user_message = self.ANALYSIS_USER_PROMPT.format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            location=job.get("location", ""),
            description=self._truncate(job.get("description", ""), 3000),
            requirements=self._truncate(job.get("requirements", ""), 1500),
            preferred_qualifications=self._truncate(
                job.get("preferred_qualifications", ""), 1000
            ),
        )

        response_text = self._chat(
            system=self.ANALYSIS_SYSTEM_PROMPT,
            user=user_message,
            temperature=0.2,
        )
        return self._parse_json_response(response_text, stage="job_analysis")

    # ------------------------------------------------------------------
    # Stage 2: Resume tailoring
    # ------------------------------------------------------------------

    def _tailor_resume(
        self,
        resume: ResumeDict,
        job: JobDict,
        job_analysis: Dict[str, Any],
    ) -> ResumeDict:
        """
        Call GPT to rewrite the resume for the target job.

        Returns:
            Updated resume dict with ``_changes`` key.
        """
        # Compact resume JSON for the prompt (skip raw_text to save tokens)
        resume_for_prompt = {k: v for k, v in resume.items() if k != "raw_text"}

        user_message = self.TAILORING_USER_PROMPT.format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            seniority_level=job_analysis.get("seniority_level", "mid"),
            role_type=job_analysis.get("role_type", "professional"),
            job_analysis=json.dumps(job_analysis, indent=2),
            resume_json=json.dumps(resume_for_prompt, indent=2),
        )

        response_text = self._chat(
            system=self.TAILORING_SYSTEM_PROMPT,
            user=user_message,
            temperature=0.4,
        )
        tailored = self._parse_json_response(response_text, stage="resume_tailoring")

        # Preserve raw_text from original
        tailored["raw_text"] = resume.get("raw_text", "")

        # Ensure _changes is a list
        if "_changes" not in tailored or not isinstance(tailored["_changes"], list):
            tailored["_changes"] = []

        return tailored

    # ------------------------------------------------------------------
    # OpenAI helper
    # ------------------------------------------------------------------

    def _chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.3,
    ) -> str:
        """
        Make a chat completion call and return the assistant message text.

        Raises:
            RuntimeError: On API errors.
        """
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=self.max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            raise RuntimeError(f"OpenAI API call failed: {exc}") from exc

    # ------------------------------------------------------------------
    # JSON parsing helper
    # ------------------------------------------------------------------

    def _parse_json_response(self, text: str, stage: str) -> Dict[str, Any]:
        """
        Parse the JSON returned by the model.

        Attempts direct json.loads first; falls back to extracting a JSON
        block from markdown code fences if the model wrapped its output.

        Raises:
            RuntimeError: If valid JSON cannot be extracted.
        """
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract from ```json ... ``` block
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        raise RuntimeError(
            f"[{stage}] Could not parse JSON from model response. "
            f"Raw response (first 300 chars): {text[:300]}"
        )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        """Truncate *text* to *max_chars* characters with an ellipsis."""
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + " … [truncated]"

    def get_analysis_prompt(self, job: JobDict) -> str:
        """
        Return the rendered analysis prompt (useful for debugging / testing).
        """
        return self.ANALYSIS_USER_PROMPT.format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            location=job.get("location", ""),
            description=self._truncate(job.get("description", ""), 3000),
            requirements=self._truncate(job.get("requirements", ""), 1500),
            preferred_qualifications=self._truncate(
                job.get("preferred_qualifications", ""), 1000
            ),
        )

    def get_tailoring_prompt(
        self, resume: ResumeDict, job: JobDict, job_analysis: Dict[str, Any]
    ) -> str:
        """
        Return the rendered tailoring prompt (useful for debugging / testing).
        """
        resume_for_prompt = {k: v for k, v in resume.items() if k != "raw_text"}
        return self.TAILORING_USER_PROMPT.format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            seniority_level=job_analysis.get("seniority_level", "mid"),
            role_type=job_analysis.get("role_type", "professional"),
            job_analysis=json.dumps(job_analysis, indent=2),
            resume_json=json.dumps(resume_for_prompt, indent=2),
        )
