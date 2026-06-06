"""
Core orchestrator for the Resume Tailor Agent.

The :class:`ResumeTailorAgent` class coordinates the full pipeline:
  1. Parse the candidate's resume (PDF or DOCX)
  2. Scrape the target job posting from a URL
  3. Tailor the resume content using GPT-4o
  4. Write the result to a new DOCX file
"""

import logging
import os
from typing import Optional

from agent.job_scraper import JobScraper
from agent.resume_parser import ResumeParser
from agent.resume_writer import ResumeWriter
from agent.tailoring_engine import TailoringEngine
from agent.utils import get_output_path, setup_logging, validate_url


class ResumeTailorAgent:
    """
    End-to-end orchestrator that turns a generic resume into a
    job-specific, ATS-optimised document.

    Args:
        openai_api_key: OpenAI API key used by the tailoring engine.
        model_name:     GPT model identifier (default: ``gpt-4o``).
        max_tokens:     Maximum tokens for each GPT completion call.
        log_level:      Python logging level string (default: ``INFO``).
        output_dir:     Directory where tailored resumes are saved
                        (default: ``outputs/``).
    """

    def __init__(
        self,
        openai_api_key: str,
        model_name: str = "gpt-4o",
        max_tokens: int = 4000,
        log_level: str = "INFO",
        output_dir: str = "outputs",
    ) -> None:
        self.logger: logging.Logger = setup_logging(log_level)
        self.output_dir = output_dir

        self.parser = ResumeParser(logger=self.logger)
        self.scraper = JobScraper(logger=self.logger)
        self.engine = TailoringEngine(
            openai_api_key=openai_api_key,
            model_name=model_name,
            max_tokens=max_tokens,
            logger=self.logger,
        )
        self.writer = ResumeWriter(logger=self.logger)

        self.logger.info(
            "ResumeTailorAgent initialised (model=%s, max_tokens=%d)",
            model_name,
            max_tokens,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        resume_path: str,
        job_url: str,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Execute the full tailoring pipeline.

        Args:
            resume_path:  Absolute or relative path to the candidate's
                          resume file (.pdf or .docx).
            job_url:      URL of the job posting to tailor against.
            output_path:  Optional explicit path for the output DOCX.
                          If omitted a timestamped path inside
                          :attr:`output_dir` is generated automatically.

        Returns:
            Path to the generated tailored resume DOCX file.

        Raises:
            FileNotFoundError: If *resume_path* does not exist.
            ValueError:        If *job_url* is not a valid HTTP/HTTPS URL.
            RuntimeError:      If any pipeline stage fails unexpectedly.
        """
        # ── Validation ────────────────────────────────────────────────
        if not os.path.exists(resume_path):
            raise FileNotFoundError(f"Resume file not found: {resume_path}")
        if not validate_url(job_url):
            raise ValueError(
                f"Invalid job URL: '{job_url}'. "
                "Please provide a full HTTP or HTTPS URL."
            )

        self.logger.info("=== Resume Tailor Agent — Pipeline Start ===")
        self.logger.info("Resume : %s", resume_path)
        self.logger.info("Job URL: %s", job_url)

        # ── Step 1: Parse resume ──────────────────────────────────────
        self.logger.info("[1/4] Parsing resume …")
        try:
            resume_data = self.parser.parse(resume_path)
        except Exception as exc:
            raise RuntimeError(f"Resume parsing failed: {exc}") from exc
        self.logger.info(
            "      Parsed resume for: %s", resume_data.get("name", "Unknown")
        )

        # ── Step 2: Scrape job posting ────────────────────────────────
        self.logger.info("[2/4] Fetching job posting …")
        try:
            job_data = self.scraper.scrape(job_url)
        except Exception as exc:
            raise RuntimeError(f"Job scraping failed: {exc}") from exc
        self.logger.info(
            "      Job: %s @ %s",
            job_data.get("title", "Unknown"),
            job_data.get("company", "Unknown"),
        )

        # ── Step 3: Tailor resume ─────────────────────────────────────
        self.logger.info("[3/4] Tailoring resume with GPT-4o …")
        try:
            tailored_resume = self.engine.tailor(resume_data, job_data)
        except Exception as exc:
            raise RuntimeError(f"Tailoring engine failed: {exc}") from exc
        self.logger.info("      Tailoring complete.")

        # ── Step 4: Write output DOCX ─────────────────────────────────
        self.logger.info("[4/4] Writing tailored resume to DOCX …")
        if output_path is None:
            output_path = get_output_path(
                base_dir=self.output_dir,
                candidate_name=tailored_resume.get("name", "candidate"),
                job_title=job_data.get("title"),
            )
        try:
            final_path = self.writer.write(tailored_resume, output_path)
        except Exception as exc:
            raise RuntimeError(f"Resume writing failed: {exc}") from exc

        self.logger.info("=== Pipeline Complete ===")
        self.logger.info("Output saved to: %s", final_path)
        return final_path

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_pipeline_summary(
        self,
        resume_path: str,
        job_url: str,
    ) -> dict:
        """
        Run the pipeline and return a summary dict instead of just the path.

        Returns a dict with keys:
          - ``output_path``  — path to the generated DOCX
          - ``candidate``    — candidate name from the resume
          - ``job_title``    — job title from the posting
          - ``company``      — company name from the posting
          - ``changes``      — list of changes made by the tailoring engine
        """
        resume_data = self.parser.parse(resume_path)
        job_data = self.scraper.scrape(job_url)
        tailored_resume = self.engine.tailor(resume_data, job_data)

        output_path = get_output_path(
            base_dir=self.output_dir,
            candidate_name=tailored_resume.get("name", "candidate"),
            job_title=job_data.get("title"),
        )
        final_path = self.writer.write(tailored_resume, output_path)

        return {
            "output_path": final_path,
            "candidate": tailored_resume.get("name", ""),
            "job_title": job_data.get("title", ""),
            "company": job_data.get("company", ""),
            "changes": tailored_resume.get("_changes", []),
        }
