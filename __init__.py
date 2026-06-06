"""
AI Resume Tailoring Agent
=========================
An intelligent agent that tailors your resume to any job posting using GPT-4o.
"""

from agent.core import ResumeTailorAgent
from agent.resume_parser import ResumeParser
from agent.job_scraper import JobScraper
from agent.tailoring_engine import TailoringEngine
from agent.resume_writer import ResumeWriter

__version__ = "1.0.0"
__author__ = "Resume Tailor Agent"
__all__ = [
    "ResumeTailorAgent",
    "ResumeParser",
    "JobScraper",
    "TailoringEngine",
    "ResumeWriter",
]
