"""
Gradio Web UI for the AI Resume Tailoring Agent.

Run with:
    python app.py

The UI provides:
  - Resume upload (PDF or DOCX)
  - Job posting URL input
  - One-click tailoring with GPT-4o
  - Downloadable tailored DOCX output
  - Plain-text preview of changes made
"""

import os
import tempfile
import traceback
from typing import Optional, Tuple

import gradio as gr

from agent.core import ResumeTailorAgent
from agent.utils import load_config, setup_logging, validate_url

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = setup_logging("INFO")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")
SUPPORTED_FORMATS = [".pdf", ".docx"]

_DESCRIPTION = """
# 🎯 AI Resume Tailoring Agent

Upload your resume and paste a job posting URL. The agent will:
1. **Parse** your resume (PDF or DOCX)
2. **Analyse** the job posting with GPT-4o
3. **Tailor** your content to maximise ATS compatibility
4. **Generate** a polished, downloadable DOCX

> **Note:** Your OpenAI API key must be set in the environment or `.env` file.
> No resume data is stored — all processing happens in memory.
"""

_FOOTER = """
---
Built with [GPT-4o](https://openai.com), [python-docx](https://python-docx.readthedocs.io), and [Gradio](https://www.gradio.app).  
Source: [github.com/resume-tailor-agent](https://github.com/resume-tailor-agent)
"""


# ---------------------------------------------------------------------------
# Core processing function
# ---------------------------------------------------------------------------

def tailor_resume(
    resume_file: Optional[str],
    job_url: str,
    progress: gr.Progress = gr.Progress(track_tqdm=True),
) -> Tuple[Optional[str], str, str]:
    """
    Main handler called by the Gradio UI.

    Args:
        resume_file: Temp path to the uploaded file (set by Gradio).
        job_url:     The job posting URL entered by the user.
        progress:    Gradio progress tracker.

    Returns:
        Tuple of:
          - output_file_path (str | None): Path for the download component.
          - changes_text (str):            Markdown-formatted change summary.
          - status_text (str):             Status / error message.
    """
    # ── Input validation ──────────────────────────────────────────────
    if resume_file is None:
        return None, "", "⚠️ Please upload a resume file (PDF or DOCX)."

    if not job_url or not job_url.strip():
        return None, "", "⚠️ Please enter a job posting URL."

    job_url = job_url.strip()
    if not validate_url(job_url):
        return (
            None,
            "",
            "⚠️ Invalid URL. Please enter a full URL starting with http:// or https://",
        )

    ext = os.path.splitext(resume_file)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        return (
            None,
            "",
            f"⚠️ Unsupported file type '{ext}'. Please upload a PDF or DOCX.",
        )

    # ── Load config ───────────────────────────────────────────────────
    try:
        config = load_config()
    except ValueError as exc:
        return (
            None,
            "",
            f"⚠️ Configuration error: {exc}\n\nPlease set your OPENAI_API_KEY.",
        )

    # ── Run the pipeline ──────────────────────────────────────────────
    try:
        progress(0, desc="Initialising agent …")
        agent = ResumeTailorAgent(
            openai_api_key=config["openai_api_key"],
            model_name=config.get("model_name", "gpt-4o"),
            max_tokens=int(config.get("max_tokens", 4000)),
            output_dir=OUTPUT_DIR,
        )

        progress(0.2, desc="Parsing resume …")
        # Parse separately so we can show progress
        resume_data = agent.parser.parse(resume_file)
        candidate_name = resume_data.get("name", "Candidate")
        logger.info("Parsed resume for: %s", candidate_name)

        progress(0.4, desc="Fetching job posting …")
        job_data = agent.scraper.scrape(job_url)
        job_title = job_data.get("title", "Position")
        company = job_data.get("company", "Company")
        logger.info("Scraped job: %s at %s", job_title, company)

        progress(0.6, desc="Tailoring with GPT-4o …")
        tailored_resume = agent.engine.tailor(resume_data, job_data)
        changes: list = tailored_resume.get("_changes", [])
        logger.info("Tailoring complete. %d changes made.", len(changes))

        progress(0.85, desc="Writing DOCX output …")
        from agent.utils import get_output_path
        output_path = get_output_path(
            base_dir=OUTPUT_DIR,
            candidate_name=candidate_name,
            job_title=job_title,
        )
        final_path = agent.writer.write(tailored_resume, output_path)

        progress(1.0, desc="Done!")

        # ── Build change summary text ─────────────────────────────────
        changes_md = _format_changes(
            changes=changes,
            candidate_name=candidate_name,
            job_title=job_title,
            company=company,
        )

        status = (
            f"✅ Resume tailored successfully!\n\n"
            f"**Candidate:** {candidate_name}\n"
            f"**Target Role:** {job_title} at {company}\n"
            f"**Output file:** `{os.path.basename(final_path)}`"
        )

        return final_path, changes_md, status

    except FileNotFoundError as exc:
        logger.error("File not found: %s", exc)
        return None, "", f"⚠️ File error: {exc}"
    except RuntimeError as exc:
        logger.error("Pipeline error: %s", exc)
        return None, "", f"⚠️ Processing error: {exc}"
    except Exception as exc:
        logger.error("Unexpected error: %s\n%s", exc, traceback.format_exc())
        return (
            None,
            "",
            f"⚠️ An unexpected error occurred: {exc}\n\nCheck the console for details.",
        )


def _format_changes(
    changes: list,
    candidate_name: str,
    job_title: str,
    company: str,
) -> str:
    """Format the list of changes into a readable Markdown string."""
    if not changes:
        return "_No specific changes were logged by the model._"

    lines = [
        f"### Changes Made for **{candidate_name}** → **{job_title}** at **{company}**\n"
    ]
    for i, change in enumerate(changes, 1):
        lines.append(f"{i}. {change}")

    lines.append(
        "\n---\n_Review the downloaded DOCX to see all changes in context._"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Example loader
# ---------------------------------------------------------------------------

def load_example_url() -> str:
    """Load a sample job URL from the examples directory."""
    example_path = os.path.join(
        os.path.dirname(__file__), "examples", "sample_job_url.txt"
    )
    if os.path.exists(example_path):
        with open(example_path) as f:
            return f.read().strip()
    return "https://jobs.lever.co/example/software-engineer"


# ---------------------------------------------------------------------------
# Gradio UI definition
# ---------------------------------------------------------------------------

def build_ui() -> gr.Blocks:
    """Construct and return the Gradio Blocks interface."""
    with gr.Blocks(
        title="AI Resume Tailoring Agent",
        theme=gr.themes.Soft(
            primary_hue="blue",
            secondary_hue="slate",
            neutral_hue="slate",
            font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui"],
        ),
        css="""
            .gr-button-primary { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); }
            .status-box { font-size: 0.95em; }
            footer { display: none !important; }
        """,
    ) as demo:
        gr.Markdown(_DESCRIPTION)

        with gr.Row(equal_height=False):
            # ── Left column: inputs ───────────────────────────────────
            with gr.Column(scale=1):
                gr.Markdown("### 📄 Upload Your Resume")
                resume_input = gr.File(
                    label="Resume File",
                    file_types=[".pdf", ".docx"],
                    type="filepath",
                    height=120,
                )

                gr.Markdown("### 🔗 Job Posting URL")
                url_input = gr.Textbox(
                    label="Job Posting URL",
                    placeholder="https://jobs.lever.co/company/job-id",
                    lines=2,
                )
                load_example_btn = gr.Button("📋 Load Example URL", size="sm", variant="secondary")

                tailor_btn = gr.Button(
                    "✨ Tailor My Resume",
                    variant="primary",
                    size="lg",
                )

                gr.Markdown(
                    "> 💡 **Tip:** Works best with LinkedIn, Greenhouse, Lever, "
                    "Indeed, Workday, and most direct career pages."
                )

            # ── Right column: outputs ─────────────────────────────────
            with gr.Column(scale=1):
                gr.Markdown("### 📥 Tailored Resume")
                output_file = gr.File(
                    label="Download Tailored Resume (.docx)",
                    interactive=False,
                )

                status_box = gr.Markdown(
                    value="_Status will appear here after tailoring._",
                    elem_classes=["status-box"],
                )

        gr.Markdown("### 📝 Changes Summary")
        changes_box = gr.Markdown(
            value="_A summary of changes made by GPT-4o will appear here._"
        )

        gr.Markdown(_FOOTER)

        # ── Event handlers ────────────────────────────────────────────
        tailor_btn.click(
            fn=tailor_resume,
            inputs=[resume_input, url_input],
            outputs=[output_file, changes_box, status_box],
            show_progress=True,
        )

        load_example_btn.click(
            fn=load_example_url,
            inputs=[],
            outputs=[url_input],
        )

    return demo


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Launch the Gradio web application."""
    logger.info("Starting AI Resume Tailoring Agent UI …")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    demo = build_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        share=False,
        show_error=True,
        favicon_path=None,
    )


if __name__ == "__main__":
    main()
