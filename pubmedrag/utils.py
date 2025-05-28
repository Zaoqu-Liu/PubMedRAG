# pubmedrag/utils.py
"""
Utility functions for PubMedRAG
"""

import logging
import re
from typing import List, Dict, Optional, Any
from datetime import datetime
from openai import OpenAI
import time

logger = logging.getLogger(__name__)


def test_api_connection(base_url: str, api_key: str, model: str = "deepseek-chat") -> bool:
    """Test if API connection is working."""
    logger.info(f"🔍 Testing API connection to {base_url}")
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say 'OK' if you can hear me."}],
        max_tokens=10,
        temperature=0
    )
    
    logger.info("✅ API connection successful")
    return True


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def clean_search_term(term: str) -> str:
    """Clean and format a search term for PubMed."""
    # Remove common prefixes
    prefixes = ["search:", "find:", "query:", "term:", "look for:"]
    term_lower = term.lower()
    for prefix in prefixes:
        if term_lower.startswith(prefix):
            term = term[len(prefix):].strip()
    
    # Remove numbering
    term = re.sub(r'^\d+[\.\)]\s*', '', term)
    
    # Ensure proper spacing around operators
    term = re.sub(r'\s+AND\s+', ' AND ', term)
    term = re.sub(r'\s+OR\s+', ' OR ', term)
    term = re.sub(r'\s+NOT\s+', ' NOT ', term)
    
    # Remove extra spaces
    term = ' '.join(term.split())
    
    return term.strip()


import os
import re
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def load_environment_config() -> Dict[str, Any]:
    """Load configuration from environment variables and .env file."""
    # Load .env file if it exists
    env_path = Path('.env')
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"📁 Loaded configuration from .env file")
    else:
        logger.info("📁 No .env file found, using environment variables")
    
    config = {}
    
    # Required settings
    required_vars = {
        'email': 'PUBMEDRAG_EMAIL',
        'llm_api_key': 'PUBMEDRAG_API_KEY',
        'llm_base_url': 'PUBMEDRAG_BASE_URL',
        'llm_model': 'PUBMEDRAG_MODEL'
    }
    
    missing_vars = []
    for key, env_var in required_vars.items():
        value = os.getenv(env_var)
        if value:
            config[key] = value
        else:
            missing_vars.append(env_var)
    
    if missing_vars:
        logger.warning(f"⚠️ Missing required environment variables: {missing_vars}")
        return None
    
    # Optional settings with defaults
    optional_vars = {
        'ncbi_api_key': ('NCBI_API_KEY', None),
        'initial_search_min': ('PUBMEDRAG_INITIAL_SEARCH_MIN', 10),
        'initial_search_max': ('PUBMEDRAG_INITIAL_SEARCH_MAX', 25),
        'followup_search_min': ('PUBMEDRAG_FOLLOWUP_SEARCH_MIN', 5),
        'followup_search_max': ('PUBMEDRAG_FOLLOWUP_SEARCH_MAX', 20),
        'temperature': ('PUBMEDRAG_TEMPERATURE', 0.3),
        'max_tokens': ('PUBMEDRAG_MAX_TOKENS', 4000),
        'embedding_model': ('PUBMEDRAG_EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'),
        'max_search_years': ('PUBMEDRAG_MAX_SEARCH_YEARS', 10),
        'min_abstract_length': ('PUBMEDRAG_MIN_ABSTRACT_LENGTH', 100),
        'exclude_letters': ('PUBMEDRAG_EXCLUDE_LETTERS', 'true'),
        'exclude_editorials': ('PUBMEDRAG_EXCLUDE_EDITORIALS', 'true'),
        'max_articles_per_search': ('PUBMEDRAG_MAX_ARTICLES_PER_SEARCH', 100),
        'search_delay': ('PUBMEDRAG_SEARCH_DELAY', 0.5),
        'max_retries': ('PUBMEDRAG_MAX_RETRIES', 3),
        'cache_enabled': ('PUBMEDRAG_CACHE_ENABLED', 'true'),
        'cache_ttl_days': ('PUBMEDRAG_CACHE_TTL_DAYS', 7),
        'db_path': ('PUBMEDRAG_DB_PATH', './pubmedrag_data'),
        'chroma_path': ('PUBMEDRAG_CHROMA_PATH', './chroma_db'),
        'log_level': ('PUBMEDRAG_LOG_LEVEL', 'INFO'),
        'log_file': ('PUBMEDRAG_LOG_FILE', 'pubmedrag.log')
    }
    
    for key, (env_var, default) in optional_vars.items():
        value = os.getenv(env_var, default)
        
        # Type conversion
        if key in ['initial_search_min', 'initial_search_max', 'followup_search_min', 
                   'followup_search_max', 'max_tokens', 'max_search_years', 
                   'min_abstract_length', 'max_articles_per_search', 'max_retries', 'cache_ttl_days']:
            config[key] = int(value)
        elif key in ['temperature', 'search_delay']:
            config[key] = float(value)
        elif key in ['exclude_letters', 'exclude_editorials', 'cache_enabled']:
            config[key] = str(value).lower() == 'true'
        else:
            config[key] = value
    
    # Validate search ranges
    config['initial_search_terms_range'] = (config['initial_search_min'], config['initial_search_max'])
    config['followup_search_terms_range'] = (config['followup_search_min'], config['followup_search_max'])
    
    logger.info("✅ Configuration loaded successfully")
    return config


def validate_pmid(pmid: str) -> bool:
    """Validate PMID format."""
    if not pmid:
        return False
    
    # PMID should be 1-8 digits with no leading zeros (except for PMID 0 which doesn't exist)
    pmid = str(pmid).strip()
    
    # Check if it's all digits
    if not pmid.isdigit():
        return False
    
    # Check length (1-8 digits)
    if len(pmid) > 8 or len(pmid) == 0:
        return False
    
    # Check for leading zeros (invalid except for single digit)
    if len(pmid) > 1 and pmid[0] == '0':
        return False
    
    # Convert to int to ensure it's a valid number
    try:
        pmid_int = int(pmid)
        # PMIDs start from 1
        return pmid_int > 0
    except ValueError:
        return False


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text:
        return ""
    
    # Convert to string if not already
    text = str(text)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Replace multiple whitespace with single space
    text = re.sub(r'\s+', ' ', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    # Remove common artifacts
    text = re.sub(r'\[PubMed\]|\[PMC free article\]|\[Free article\]', '', text)
    
    return text


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """Setup logging configuration."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create logs directory if it doesn't exist
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    # Reduce noise from external libraries
    logging.getLogger('openai').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('chromadb').setLevel(logging.WARNING)


def create_env_template() -> None:
    """Create a .env.template file with all configuration options."""
    template_path = Path('.env.template')
    
    template_content = '''# PubMedRAG Configuration File
# Copy this file to .env and fill in your settings

# ====================
# Required Settings
# ====================

# Email for NCBI/PubMed access (required by NCBI terms)
PUBMEDRAG_EMAIL=your-email@university.edu

# AI Model Configuration
PUBMEDRAG_API_KEY=your-api-key-here
PUBMEDRAG_BASE_URL=https://api.deepseek.com/v1
PUBMEDRAG_MODEL=deepseek-chat

# ====================
# Optional Settings
# ====================

# NCBI API Key (optional but recommended for higher rate limits)
# Get one at: https://www.ncbi.nlm.nih.gov/account/
NCBI_API_KEY=your-ncbi-api-key

# Search Configuration
PUBMEDRAG_INITIAL_SEARCH_MIN=10
PUBMEDRAG_INITIAL_SEARCH_MAX=25
PUBMEDRAG_FOLLOWUP_SEARCH_MIN=5
PUBMEDRAG_FOLLOWUP_SEARCH_MAX=20

# Quality Control Settings
PUBMEDRAG_MAX_SEARCH_YEARS=10
PUBMEDRAG_MIN_ABSTRACT_LENGTH=100
PUBMEDRAG_EXCLUDE_LETTERS=true
PUBMEDRAG_EXCLUDE_EDITORIALS=true

# Model Parameters
PUBMEDRAG_TEMPERATURE=0.3
PUBMEDRAG_MAX_TOKENS=4000

# Performance Settings
PUBMEDRAG_MAX_ARTICLES_PER_SEARCH=100
PUBMEDRAG_SEARCH_DELAY=0.5
PUBMEDRAG_MAX_RETRIES=3

# Cache Settings
PUBMEDRAG_CACHE_ENABLED=true
PUBMEDRAG_CACHE_TTL_DAYS=7

# ====================
# Advanced Settings
# ====================

# Embedding Model
PUBMEDRAG_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Database Settings
PUBMEDRAG_DB_PATH=./pubmedrag_data
PUBMEDRAG_CHROMA_PATH=./chroma_db

# Logging
PUBMEDRAG_LOG_LEVEL=INFO
PUBMEDRAG_LOG_FILE=pubmedrag.log

# ====================
# Alternative Providers
# ====================

# For OpenAI
# PUBMEDRAG_BASE_URL=https://api.openai.com/v1
# PUBMEDRAG_MODEL=gpt-3.5-turbo

# For custom providers
# PUBMEDRAG_BASE_URL=https://your-custom-api.com/v1
# PUBMEDRAG_MODEL=your-model-name
'''
    
    with open(template_path, 'w') as f:
        f.write(template_content)
    
    logger.info(f"📝 Created .env.template file at {template_path}")


def format_reference(citation: Dict[str, Any], style: str = "numbered") -> str:
    """Format a citation with proper title, journal, date, and PMID URL."""
    number = citation.get('number', '')
    title = citation.get('title', '').strip()
    journal = citation.get('journal', '').strip()
    pub_date = citation.get('pub_date', '').strip()
    pmid = citation.get('pmid', '').strip()
    authors = citation.get('authors', '').strip()
    
    # Debug: log PMID for troubleshooting
    logger.debug(f"Formatting citation {number}: PMID={pmid}, Title={title[:30]}...")
    
    # Validate and clean PMID
    if not validate_pmid(pmid):
        logger.warning(f"Invalid PMID format in citation {number}: {pmid}")
        pmid = ""
    
    # Clean up and validate title
    if not title or title.lower() in ['no title', 'title not available']:
        title = "Title not available"
    else:
        title = clean_text(title).rstrip('.,;')
    
    # Clean up and validate journal
    if not journal or journal.lower() in ['unknown journal', 'unknown', '', 'journal not available']:
        journal = "Unknown journal"
    else:
        journal = clean_text(journal).rstrip('.,;')
    
    # Clean up publication date
    if not pub_date or pub_date.lower() in ['date unknown', 'unknown', '', 'date not available']:
        pub_date = "Unknown date"
    else:
        pub_date = clean_text(pub_date).rstrip('.,;')
    
    # Format authors (truncate if too long)
    if authors and len(authors) > 100:
        authors = authors[:97] + "..."
    
    # Generate PMID URL
    pmid_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
    
    # Format based on style
    if style == "numbered":
        if authors:
            ref = f"[{number}] {authors}. {title}. {journal}. {pub_date}."
        else:
            ref = f"[{number}] {title}. {journal}. {pub_date}."
        
        if pmid_url:
            ref += f" {pmid_url}"
    else:
        # Default format
        ref = f"[{number}] {title}. {journal}. {pub_date}."
        if pmid_url:
            ref += f" {pmid_url}"
    
    return ref


def format_references_list(citations: List[Dict[str, Any]], style: str = "numbered") -> str:
    """Format a list of citations with improved formatting."""
    if not citations:
        return "No references available."
    
    # Create header with proper alignment
    header = "📚 References"
    separator = "─" * 80  # Fixed width for better alignment
    
    formatted = f"\n{header}\n{separator}\n"
    
    for citation in citations:
        ref = format_reference(citation, style)
        formatted += f"{ref}\n"
    
    return formatted


def get_pubmed_url(pmid: str) -> str:
    """Generate PubMed URL from PMID."""
    if pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    return ""


def get_doi_url(doi: str) -> str:
    """Generate DOI URL."""
    if doi:
        # Clean DOI
        doi = doi.replace("doi:", "").replace("DOI:", "").strip()
        return f"https://doi.org/{doi}"
    return ""


def estimate_search_time(num_terms: int, articles_per_term: int) -> str:
    """Estimate time for search operation."""
    # Rough estimates
    time_per_search = 2  # seconds
    time_per_article = 0.05  # seconds for processing
    
    total_seconds = (num_terms * time_per_search) + (num_terms * articles_per_term * time_per_article)
    
    if total_seconds < 60:
        return f"~{int(total_seconds)} seconds"
    elif total_seconds < 300:
        return f"~{int(total_seconds/60)} minutes"
    else:
        return f"~{int(total_seconds/60)} minutes"


def extract_keywords_from_question(question: str) -> List[str]:
    """Simple keyword extraction for reference (not used in main logic)."""
    # Simple tokenization - mainly for display purposes
    words = question.lower().split()
    keywords = [word.strip('.,!?;()[]{}') for word in words if len(word) > 2]
    return keywords[:10]  # Return first 10 words for display


def analyze_question_complexity(question: str) -> Dict[str, Any]:
    """Simplified question analysis for display purposes only."""
    keywords = extract_keywords_from_question(question)
    
    return {
        "keywords": keywords,
        "complexity_score": len(keywords),
        "question_types": {},
        "suggested_search_terms": 15  # Default to 15 search terms (within the 10-30 range)
    }


def format_time_ago(timestamp: str) -> str:
    """Format timestamp as 'X days/hours/minutes ago'."""
    try:
        # Handle different timestamp formats
        if timestamp.endswith('Z'):
            timestamp = timestamp[:-1] + '+00:00'
        
        dt = datetime.fromisoformat(timestamp)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"
    except (ValueError, TypeError):
        return "unknown time"


def print_question_analysis(analysis: Dict[str, Any]):
    """Simplified question analysis display."""
    print(f"\n📊 Question Analysis: {len(analysis['keywords'])} key terms identified")
    print("─" * 40)


def create_search_summary(search_history: Dict[str, Any]) -> str:
    """Create a summary of search history."""
    total_questions = len(search_history.get('queries', []))
    total_articles = len(search_history.get('indexed_pmids', []))
    total_terms = len(search_history.get('all_search_terms', []))
    topic = search_history.get('topic', 'General research')
    
    summary = f"""
📊 Search Summary
{'─' * 50}
• Topic: {topic}
• Questions asked: {total_questions}
• Articles indexed: {total_articles}
• Search terms used: {total_terms}
• Session started: {format_time_ago(search_history.get('created_at', ''))}

Recent Questions:
"""
    
    for i, query in enumerate(search_history.get('queries', [])[-5:], 1):
        summary += f"{i}. {query['question'][:80]}{'...' if len(query['question']) > 80 else ''}\n"
        summary += f"   → {len(query['new_pmids'])} new articles\n"
    
    return summary


def clean_display_text(text: str, max_width: int = 80) -> str:
    """Clean and format text for terminal display."""
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    # Break long lines
    if len(text) > max_width:
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            if current_length + len(word) + 1 <= max_width:
                current_line.append(word)
                current_length += len(word) + 1
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_length = len(word)
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return '\n'.join(lines)
    
    return text


def format_terminal_table(headers: List[str], rows: List[List[str]], max_width: int = 80) -> str:
    """Format data as a terminal-friendly table."""
    if not headers or not rows:
        return ""
    
    # Calculate column widths
    col_widths = [len(header) for header in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Adjust widths if total exceeds max_width
    total_width = sum(col_widths) + len(headers) * 3  # Account for separators
    if total_width > max_width:
        # Proportionally reduce column widths
        reduction_factor = (max_width - len(headers) * 3) / sum(col_widths)
        col_widths = [max(8, int(w * reduction_factor)) for w in col_widths]
    
    # Format table
    separator = "+" + "+".join(["-" * (w + 2) for w in col_widths]) + "+"
    
    # Header
    header_row = "|" + "|".join([f" {headers[i]:<{col_widths[i]}} " for i in range(len(headers))]) + "|"
    
    # Rows
    table_rows = []
    for row in rows:
        formatted_cells = []
        for i, cell in enumerate(row):
            if i < len(col_widths):
                cell_str = str(cell)[:col_widths[i]]  # Truncate if too long
                formatted_cells.append(f" {cell_str:<{col_widths[i]}} ")
        table_rows.append("|" + "|".join(formatted_cells) + "|")
    
    # Combine
    result = [separator, header_row, separator]
    result.extend(table_rows)
    result.append(separator)
    
    return "\n".join(result)