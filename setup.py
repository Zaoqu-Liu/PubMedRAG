# setup.py
from setuptools import setup, find_packages
import os

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))

# Read long description from README
try:
    with open(os.path.join(this_directory, "README.md"), "r", encoding="utf-8") as fh:
        long_description = fh.read()
except FileNotFoundError:
    long_description = "PubMedRAG - Question-Driven Medical Literature Research Assistant"

# Read requirements
try:
    with open(os.path.join(this_directory, "requirements.txt"), "r", encoding="utf-8") as fh:
        requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]
except FileNotFoundError:
    requirements = [
        "biopython>=1.79",
        "langchain>=0.1.0",
        "sentence-transformers>=2.2.0",
        "chromadb>=0.4.0",
        "openai>=1.0.0",
        "colorama>=0.4.4",
        "tqdm>=4.65.0"
    ]

setup(
    name="pubmedrag",
    version="2.0.0",
    author="PubMedRAG Team",
    author_email="contact@pubmedrag.com",
    description="Question-Driven Medical Literature Research Assistant for PubMed",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pubmedrag/pubmedrag",
    project_urls={
        "Bug Reports": "https://github.com/pubmedrag/pubmedrag/issues",
        "Source": "https://github.com/pubmedrag/pubmedrag",
        "Documentation": "https://docs.pubmedrag.com",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Healthcare Industry",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Text Processing :: Linguistic",
        "Environment :: Console",
        "Natural Language :: English",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.10",
            "black>=21.0",
            "flake8>=3.8",
            "isort>=5.0",
            "mypy>=0.800",
            "pre-commit>=2.20.0",
        ],
        "docs": [
            "sphinx>=4.0",
            "sphinx-rtd-theme>=1.0",
            "myst-parser>=0.15",
            "autodoc>=0.5",
        ],
    },
    entry_points={
        "console_scripts": [
            "pubmedrag=pubmedrag.cli:main",
            "pmrag=pubmedrag.cli:main",  # Short alias
        ],
    },
    keywords=[
        "pubmed", "rag", "medical", "research", "literature", "nlp", "ai",
        "question-answering", "biomedical", "healthcare", "scientific",
        "retrieval-augmented-generation", "vector-search", "embeddings"
    ],
    include_package_data=True,
    package_data={
        "pubmedrag": [
            "*.txt",
            "*.md",
            "*.json",
        ],
    },
    zip_safe=False,
    license="MIT",
    platforms=["any"],
)