# AI Resume Tailoring Agent

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenAI GPT-4o](https://img.shields.io/badge/OpenAI-GPT--4o-412991.svg)](https://platform.openai.com/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

An intelligent, end-to-end Python agent that tailors your resume to any job posting using GPT-4o. Upload a PDF or DOCX resume, provide a job URL, and receive a polished, ATS-optimised DOCX — in seconds.

---

## Features

- **Universal resume parsing** — handles both PDF and DOCX formats with structured field extraction (name, contact, summary, experience, education, skills, certifications)
- **Any job board** — fetches and parses job postings from LinkedIn, Greenhouse, Lever, Indeed, Workday, and any generic career page
- **Two-stage GPT-4o pipeline** — first analyses the job for ATS keywords and requirements, then tailors resume content with precise, instructed rewrites
- **Zero fabrication guarantee** — system prompt enforces factual accuracy; only language, ordering, and keyword alignment are changed
- **ATS-friendly DOCX output** — clean, professional Word document with proper heading structure, no tables or text boxes that break ATS parsers
- **Gradio web UI** — one-page interface with file upload, URL input, progress tracking, and instant download
- **Python API** — import `ResumeTailorAgent` directly into any script or pipeline
- **Fully typed** — type hints throughout; mypy compatible
- **Comprehensive test suite** — pytest with mocking for all three core modules

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AI Resume Tailoring Agent                   │
│                                                                 │
│   ┌──────────────┐    ┌──────────────┐    ┌─────────────────┐  │
│   │  Resume File │    │  Job Posting │    │   GPT-4o        │  │
│   │  (PDF/DOCX)  │    │     URL      │    │   (OpenAI API)  │  │
│   └──────┬───────┘    └──────┬───────┘    └────────┬────────┘  │
│          │                  │                      │           │
│          ▼                  ▼                      │           │
│   ┌──────────────┐    ┌──────────────┐             │           │
│   │ ResumeParser │    │  JobScraper  │             │           │
│   │              │    │              │             │           │
│   │ pdfplumber / │    │ requests +   │             │           │
│   │ python-docx  │    │ BeautifulSoup│             │           │
│   └──────┬───────┘    └──────┬───────┘             │           │
│          │                  │                      │           │
│          └─────────┬────────┘                      │           │
│                    │                               │           │
│                    ▼                               │           │
│          ┌──────────────────┐                      │           │
│          │  TailoringEngine │◄─────────────────────┘           │
│          │                  │                                   │
│          │  Stage 1: Analyse job → extract keywords            │
│          │  Stage 2: Rewrite resume → ATS-optimised            │
│          └────────┬─────────┘                                  │
│                   │                                            │
│                   ▼                                            │
│          ┌──────────────────┐                                  │
│          │  ResumeWriter    │                                  │
│          │                  │                                  │
│          │  python-docx     │                                  │
│          │  ATS-friendly    │                                  │
│          └────────┬─────────┘                                  │
│                   │                                            │
│                   ▼                                            │
│          ┌──────────────────┐                                  │
│          │  Tailored Resume │                                  │
│          │  (.docx output)  │                                  │
│          └──────────────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- Python 3.9 or higher
- An [OpenAI API key](https://platform.openai.com/api-keys) with access to `gpt-4o`

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/resume-tailor-agent/resume-tailor-agent.git
cd resume-tailor-agent
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Or install as a package with development extras:

```bash
pip install -e ".[dev]"
```

### 4. Configure your environment

```bash
cp .env.example .env
```

Open `.env` and set your `OPENAI_API_KEY`:

```
OPENAI_API_KEY=sk-...your-key-here...
MODEL_NAME=gpt-4o
MAX_TOKENS=4000
LOG_LEVEL=INFO
```

---

## Usage

### Web UI (Gradio)

```bash
python app.py
```

Open [http://localhost:7860](http://localhost:7860) in your browser.

1. Upload your resume (PDF or DOCX)
2. Paste the job posting URL
3. Click **Tailor My Resume**
4. Download the generated `.docx` and review the changes summary

### Python API

```python
from agent.core import ResumeTailorAgent
from agent.utils import load_config

config = load_config()

agent = ResumeTailorAgent(
    openai_api_key=config["openai_api_key"],
    model_name=config["model_name"],    # "gpt-4o"
    max_tokens=config["max_tokens"],    # 4000
    output_dir="outputs",
)

# Returns the path to the generated DOCX
output_path = agent.run(
    resume_path="my_resume.pdf",
    job_url="https://boards.greenhouse.io/acme/jobs/12345",
)

print(f"Saved to: {output_path}")
```

### With change summary

```python
summary = agent.get_pipeline_summary(
    resume_path="my_resume.docx",
    job_url="https://jobs.lever.co/company/job-id",
)

print(f"Role   : {summary['job_title']} at {summary['company']}")
print(f"Output : {summary['output_path']}")
print("Changes:")
for change in summary["changes"]:
    print(f"  • {change}")
```

### Command-line entry point

After `pip install -e .`:

```bash
resume-tailor
# Launches the Gradio UI
```

---

## How It Works

### Step 1 — Resume Parsing

`ResumeParser` extracts raw text from your PDF (via `pdfplumber`) or DOCX (via `python-docx`). It then uses regex-based section detection to segment the text into structured fields: name, contact info, summary, a list of experience entries (each with title, company, dates, and bullet points), education, skills, and certifications.

### Step 2 — Job Scraping

`JobScraper` fetches the job posting HTML using `requests` with a realistic browser User-Agent. For known boards (Greenhouse, Lever, LinkedIn, Indeed, Workday), it uses board-specific CSS selectors. For all other URLs it falls back to `readability-lxml` article extraction followed by BeautifulSoup heuristics. The raw description is split into main description, requirements, and preferred qualifications sections.

### Step 3 — Two-Stage GPT-4o Tailoring

**Stage 1 — Job Analysis:** A structured prompt asks GPT-4o to extract must-have skills, nice-to-have skills, top responsibilities, ATS keywords, seniority level, and culture signals from the job posting. Returns a JSON object.

**Stage 2 — Resume Tailoring:** A second prompt provides the job analysis and the current resume JSON. GPT-4o rewrites the summary, reorders and enhances experience bullets to front-load the most relevant achievements, and ensures all relevant skills are present — while a strict system prompt forbids fabrication. Returns the complete updated resume JSON plus a `_changes` list.

### Step 4 — DOCX Generation

`ResumeWriter` constructs a fresh Word document using `python-docx` with professional formatting: name as a large heading, contact line, a ruled separator, and clean sections for Summary, Experience, Education, Skills, and Certifications. The output is ATS-safe (no tables, columns, or text boxes).

---

## Supported File Formats

| Format | Parser | Notes |
|--------|--------|-------|
| `.pdf` | pdfplumber | Text-based PDFs only; scanned image PDFs are not supported |
| `.docx` | python-docx | Full support |
| `.doc` | python-docx | Limited support (older Word format) |

---

## Output

Tailored resumes are saved to the `outputs/` directory with a timestamped filename:

```
outputs/Jane_Doe_Senior_Backend_Engineer_20240315_143022.docx
```

The `outputs/` directory is included in `.gitignore` so generated files are not committed to version control.

---

## Running Tests

```bash
pytest tests/ -v
```

With coverage:

```bash
pytest tests/ -v --cov=agent --cov-report=term-missing
```

---

## Project Structure

```
resume-tailor-agent/
├── README.md                   # This file
├── .gitignore
├── .env.example                # Environment variable template
├── requirements.txt
├── setup.py                    # Package configuration & CLI entry point
├── LICENSE                     # MIT License
├── app.py                      # Gradio web UI entry point
├── agent/
│   ├── __init__.py
│   ├── core.py                 # Main orchestrator: ResumeTailorAgent
│   ├── resume_parser.py        # PDF/DOCX parsing
│   ├── job_scraper.py          # Job posting fetching and parsing
│   ├── tailoring_engine.py     # GPT-4o tailoring logic
│   ├── resume_writer.py        # DOCX generation
│   └── utils.py                # Logging, config, helpers
├── templates/
│   └── README.md
├── outputs/                    # Generated resumes (git-ignored)
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   ├── test_resume_parser.py
│   ├── test_job_scraper.py
│   └── test_tailoring_engine.py
└── examples/
    ├── sample_job_url.txt
    └── README.md               # Usage examples
```

---

## Contributing

Contributions are welcome! Here is how to get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes with type hints and docstrings
4. Add or update tests in `tests/`
5. Run the test suite: `pytest tests/ -v`
6. Format your code: `black . && isort .`
7. Submit a pull request with a clear description of what changed

### Development setup

```bash
pip install -e ".[dev]"
pre-commit install   # optional, if .pre-commit-config.yaml is added
```

### Reporting issues

Please open an issue on GitHub with:
- Python version and OS
- The exact error message / traceback
- Steps to reproduce (anonymise any resume content)

---

## Privacy Note

This tool sends your resume content and the job posting text to the OpenAI API for processing. Do not use personal resumes on shared or untrusted machines. Review [OpenAI's data usage policy](https://openai.com/policies/api-data-usage-policies) before use.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgements

- [OpenAI](https://openai.com) for GPT-4o
- [python-docx](https://python-docx.readthedocs.io) for Word document generation
- [pdfplumber](https://github.com/jsvine/pdfplumber) for PDF text extraction
- [Gradio](https://www.gradio.app) for the web UI framework
- [readability-lxml](https://github.com/buriy/python-readability) for article extraction
