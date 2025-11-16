"""
Setup script for Automate Jira
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    requirements = [
        line.strip()
        for line in requirements_file.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="automate-jira",
    version="2.1.0",
    description="Comprehensive time tracking and reporting tool for Jira",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Team",
    author_email="your-email@company.com",
    url="https://github.com/yourcompany/automate-jira",
    packages=find_packages(include=["src", "src.*"]),
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.11.0",
            "responses>=0.23.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.5.0",
            "isort>=5.12.0",
        ],
        "excel": ["openpyxl>=3.1.0"],
        "cache": ["requests-cache>=1.1.0"],
        "cli": ["click>=8.1.0", "rich>=13.0.0", "tqdm>=4.66.0"],
    },
    entry_points={
        "console_scripts": [
            "jira-tracker=scripts.generate_report:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Bug Tracking",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    keywords="jira time-tracking reporting worklog",
)
