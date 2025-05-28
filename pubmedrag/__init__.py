# pubmedrag/__init__.py
"""
PubMedRAG - Question-Driven Medical Literature Research Assistant

A powerful RAG (Retrieval-Augmented Generation) system that enables 
researchers to ask questions and get evidence-based answers from PubMed literature.

Key Features:
- 🔍 Question-driven literature search
- 📚 Automatic PubMed article retrieval
- 🧠 Intelligent answer generation with citations
- 💾 Session management and caching
- 🎯 Incremental knowledge base building

Author: PubMedRAG Team
License: MIT
"""

from .core import (
    QuestionDrivenRAG,
    PubMedArticle,
    SearchHistory,
    fetch_pubmed_articles,
    parse_pubmed_text_record,
    parse_pubmed_xml_record,
    chunk_abstracts,
    ChromaDBManager,
    validate_pmid,
    clean_text
)

from .cache import (
    SessionCache,
    VectorDBCache,
    TopicManager
)

from .utils import (
    test_api_connection,
    validate_email,
    clean_search_term,
    format_reference,
    format_references_list,
    get_pubmed_url,
    get_doi_url,
    estimate_search_time,
    format_time_ago,
    create_search_summary,
    load_environment_config,
    setup_logging,
    create_env_template
)

__version__ = "2.0.0"
__author__ = "Zaoqu Liu"
__email__ = "liuzaoqu@163.com"

# Main components for easy import
__all__ = [
    # Core classes
    "QuestionDrivenRAG",
    "PubMedArticle",
    "SearchHistory",
    "ChromaDBManager",
    
    # Cache management
    "SessionCache",
    "VectorDBCache",
    "TopicManager",
    
    # Core functions
    "fetch_pubmed_articles",
    "parse_pubmed_text_record",
    "parse_pubmed_xml_record",
    "chunk_abstracts",
    "validate_pmid",
    "clean_text",
    
    # Utility functions
    "test_api_connection",
    "validate_email",
    "clean_search_term",
    "format_reference",
    "format_references_list",
    "get_pubmed_url",
    "get_doi_url",
    "estimate_search_time",
    "format_time_ago",
    "create_search_summary",
    "load_environment_config",
    "setup_logging",
    "create_env_template"
]

# Package metadata
__metadata__ = {
    "name": "pubmedrag",
    "version": __version__,
    "description": "Question-Driven Medical Literature Research Assistant",
    "author": __author__,
    "email": __email__,
    "url": "https://github.com/Zaoqu-Liu/PubMedRAG",
    "license": "MIT",
    "keywords": ["pubmed", "rag", "medical", "research", "question-answering", "nlp", "ai"],
    "classifiers": [
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Healthcare Industry",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ]
}