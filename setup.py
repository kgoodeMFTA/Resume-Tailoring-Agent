"""
Setup configuration for the AI Resume Tailoring Agent package.

Install for development:
    pip install -e .

Install from source:
    pip install .
"""

from setuptools import find_packages, setup

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", encoding="utf-8") as fh:
    install_requires = [
        line.strip()
        for line in fh
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="resume-tailor-agent",
    version="1.0.0",
    author="Resume Tailor Agent Contributors",
    author_email="contact@resume-tailor-agent.dev",
    description=(
        "An AI-powered agent that tailors your resume to any job posting "
        "using GPT-4o, with ATS optimisation and a Gradio web UI."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/resume-tailor-agent/resume-tailor-agent",
    project_urls={
        "Bug Tracker": "https://github.com/resume-tailor-agent/resume-tailor-agent/issues",
        "Documentation": "https://github.com/resume-tailor-agent/resume-tailor-agent#readme",
        "Source": "https://github.com/resume-tailor-agent/resume-tailor-agent",
    },
    packages=find_packages(exclude=["tests*", "examples*"]),
    python_requires=">=3.9",
    install_requires=install_requires,
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0",
            "isort>=5.12",
            "mypy>=1.0",
            "flake8>=6.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "resume-tailor=app:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Office/Business",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    keywords=[
        "resume", "cv", "tailoring", "ats", "openai", "gpt-4o",
        "job-application", "career", "nlp", "gradio",
    ],
    include_package_data=True,
    zip_safe=False,
)
