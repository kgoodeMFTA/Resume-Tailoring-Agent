"""
Utility functions for the Resume Tailor Agent.

Provides logging configuration, environment loading, URL validation,
and filename sanitization helpers used across the agent pipeline.
"""

import logging
import os
import re
import unicodedata
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configure and return a named logger for the agent.

    Args:
        level: Logging level string, e.g. "DEBUG", "INFO", "WARNING".

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("resume_tailor")
    logger.setLevel(numeric_level)
    return logger


def load_config() -> dict:
    """
    Load configuration from a .env file (if present) and environment variables.

    Expected environment variables:
        - OPENAI_API_KEY  (required)
        - MODEL_NAME      (default: gpt-4o)
        - MAX_TOKENS      (default: 4000)
        - LOG_LEVEL       (default: INFO)

    Returns:
        A dict containing the resolved configuration values.

    Raises:
        ValueError: If OPENAI_API_KEY is not set.
    """
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. "
            "Copy .env.example to .env and add your key, or export the variable."
        )

    return {
        "openai_api_key": api_key,
        "model_name": os.getenv("MODEL_NAME", "gpt-4o"),
        "max_tokens": int(os.getenv("MAX_TOKENS", "4000")),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
    }


def validate_url(url: str) -> bool:
    """
    Validate that a string is a well-formed HTTP or HTTPS URL.

    Args:
        url: The URL string to validate.

    Returns:
        True if the URL is valid, False otherwise.
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Convert an arbitrary string into a safe filename.

    Replaces whitespace with underscores, strips non-alphanumeric characters
    (except hyphens and underscores), normalises unicode, and truncates to
    *max_length* characters.

    Args:
        name:       The raw string to sanitize.
        max_length: Maximum allowed length of the returned filename.

    Returns:
        A sanitized filename string (without extension).
    """
    # Normalize unicode characters to ASCII equivalents where possible
    normalized = unicodedata.normalize("NFKD", name)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")

    # Replace whitespace with underscores
    ascii_str = re.sub(r"\s+", "_", ascii_str)

    # Keep only alphanumeric, hyphens, underscores, and dots
    ascii_str = re.sub(r"[^\w\-.]", "", ascii_str)

    # Collapse repeated underscores/hyphens
    ascii_str = re.sub(r"[_\-]{2,}", "_", ascii_str)

    # Strip leading/trailing underscores and hyphens
    ascii_str = ascii_str.strip("_-.")

    return ascii_str[:max_length] if ascii_str else "resume_output"


def get_output_path(
    base_dir: str,
    candidate_name: str,
    job_title: Optional[str] = None,
) -> str:
    """
    Build a timestamped output file path for a tailored resume.

    Args:
        base_dir:       Directory where the output file will be saved.
        candidate_name: Name of the candidate (used in the filename).
        job_title:      Optional job title to include in the filename.

    Returns:
        Absolute path string ending in `.docx`.
    """
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = sanitize_filename(candidate_name or "candidate")
    safe_title = sanitize_filename(job_title or "tailored")

    filename = f"{safe_name}_{safe_title}_{timestamp}.docx"
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, filename)
