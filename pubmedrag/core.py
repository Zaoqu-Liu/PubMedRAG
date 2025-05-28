# pubmedrag/core.py
"""
Core functionality for PubMedRAG - Question-driven medical literature search and QA system
"""

import os
import uuid
import logging
import time
import json
import re
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime

from Bio import Entrez
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import DEFAULT_TENANT, DEFAULT_DATABASE, Settings
from openai import OpenAI

# Disable telemetry
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["POSTHOG_DISABLED"] = "True" 
os.environ["TOKENIZERS_PARALLELISM"] = "false"

logger = logging.getLogger(__name__)


@dataclass
class PubMedArticle:
    """Structure to hold PubMed article information."""
    pmid: str
    title: str
    abstract: str
    doi: str = ""
    authors: str = ""
    journal: str = ""
    pub_date: str = ""
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "pmid": self.pmid,
            "title": self.title,
            "abstract": self.abstract,
            "doi": self.doi,
            "authors": self.authors,
            "journal": self.journal,
            "pub_date": self.pub_date
        }


@dataclass
class SearchHistory:
    """Track search history for a session."""
    session_id: str
    queries: List[Dict[str, Any]] = field(default_factory=list)
    all_search_terms: Set[str] = field(default_factory=set)
    indexed_pmids: Set[str] = field(default_factory=set)
    collection_name: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    topic: str = ""  # Added topic field for better cache management
    
    def add_query(self, question: str, search_terms: List[str], pmids: List[str]):
        """Add a query to history."""
        self.queries.append({
            "question": question,
            "search_terms": search_terms,
            "timestamp": datetime.now().isoformat(),
            "new_pmids": pmids
        })
        self.all_search_terms.update(search_terms)
        self.indexed_pmids.update(pmids)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "queries": self.queries,
            "all_search_terms": list(self.all_search_terms),
            "indexed_pmids": list(self.indexed_pmids),
            "collection_name": self.collection_name,
            "created_at": self.created_at.isoformat(),
            "topic": self.topic
        }


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


def parse_pubmed_text_record(record_text: str) -> List[PubMedArticle]:
    """Parse PubMed records from text format to extract structured information."""
    articles = []
    
    # Split records by PMID patterns
    records = re.split(r'\n(?=\d+\. )', record_text)
    
    for record in records:
        if not record.strip():
            continue
            
        # Extract PMID
        pmid_match = re.search(r'^(\d+)\.', record)
        if not pmid_match:
            continue
        pmid = pmid_match.group(1)
        
        # Extract title - this should be the main title after the PMID
        title_match = re.search(r'^\d+\.\s*(.+?)(?:\n|$)', record, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else ""
        
        # Remove any journal/source info that might be mixed in the title
        # Title should not contain publication info
        if title and ('.' in title and ('doi:' in title.lower() or 'epub' in title.lower() or re.search(r'\d{4}', title))):
            # Try to extract just the title part before publication info
            title_parts = title.split('.')
            for i, part in enumerate(title_parts):
                if any(x in part.lower() for x in ['doi', 'epub', 'pmid', 'j ', 'journal']):
                    title = '.'.join(title_parts[:i]).strip()
                    break
        
        # Extract DOI
        doi_match = re.search(r'DOI:\s*([^\s\n]+)', record)
        doi = doi_match.group(1) if doi_match else ""
        
        # Extract authors
        authors_match = re.search(r'Author[s]?:\s*(.+?)(?:\n\n|\n[A-Z]|$)', record, re.DOTALL)
        authors = authors_match.group(1).strip().replace('\n', ' ') if authors_match else ""
        
        # Extract journal - look for patterns like "Journal Name. Year" or "Source: Journal Name"
        journal_patterns = [
            r'(?:Source:|Journal:)\s*(.+?)(?:\n|$)',
            r'(?:^|\n)([A-Z][^.\n]+\.)\s*\d{4}',  # Journal name followed by year
            r'\.([A-Z][A-Za-z\s&]+)\.\s*\d{4}',   # Journal in middle of citation
        ]
        
        journal = ""
        for pattern in journal_patterns:
            journal_match = re.search(pattern, record)
            if journal_match:
                journal = journal_match.group(1).strip()
                # Clean up journal name
                journal = journal.rstrip('.,;')
                break
        
        # If no journal found, try to extract from common PubMed formats
        if not journal:
            # Look for pattern like ". Journal Name. Year Month"
            lines = record.split('\n')
            for line in lines:
                if re.search(r'^\s*[A-Z][A-Za-z\s&]+\.\s*\d{4}', line):
                    journal = line.split('.')[0].strip()
                    break
        
        # Extract publication date
        date_patterns = [
            r'(\d{4}\s+[A-Za-z]+(?:\s+\d+)?)',  # 2024 Aug 30
            r'(\d{4})',  # Just year
        ]
        
        pub_date = ""
        for pattern in date_patterns:
            date_match = re.search(pattern, record)
            if date_match:
                pub_date = date_match.group(1)
                break
        
        # Extract abstract - look for various patterns
        abstract_patterns = [
            r'(?:Abstract[:\s]*)(.*?)(?:\n\n|$)',
            r'(?:BACKGROUND[:\s]*)(.*?)(?:\n\n|$)',
            r'(?:OBJECTIVE[:\s]*)(.*?)(?:\n\n|$)',
            r'(?:INTRODUCTION[:\s]*)(.*?)(?:\n\n|$)'
        ]
        
        abstract = ""
        for pattern in abstract_patterns:
            abstract_match = re.search(pattern, record, re.DOTALL | re.IGNORECASE)
            if abstract_match:
                abstract = abstract_match.group(1).strip()
                break
        
        # If no abstract found, try to extract text after title and journal info
        if not abstract and title:
            remaining_text = record[record.find(title) + len(title):]
            # Remove publication info and get the actual abstract
            lines = remaining_text.split('\n')
            abstract_lines = []
            for line in lines:
                line = line.strip()
                if line and not any(x in line.lower() for x in ['doi:', 'pmid:', 'author:', 'epub', 'source:']):
                    abstract_lines.append(line)
            abstract = ' '.join(abstract_lines)
        
        # Clean up abstract
        abstract = re.sub(r'\n+', ' ', abstract)
        abstract = re.sub(r'\s+', ' ', abstract).strip()
        
        # Skip if no meaningful content
        if not title or len(abstract) < 50:
            continue
        
        # Create article object
        article = PubMedArticle(
            pmid=pmid,
            title=clean_text(title),
            abstract=clean_text(abstract),
            doi=clean_text(doi),
            authors=clean_text(authors),
            journal=clean_text(journal),
            pub_date=clean_text(pub_date)
        )
        
        articles.append(article)
    
    return articles


def parse_pubmed_xml_record(record: Dict[str, Any]) -> Optional[PubMedArticle]:
    """Parse a single PubMed record from XML/dict format with enhanced validation and data cleaning."""
    try:
        # Extract and validate PMID
        pmid = record.get("Id", "")
        if not pmid:
            logger.warning("Record missing PMID, skipping")
            return None
            
        # Ensure PMID is string and validate format
        pmid = str(pmid).strip()
        if not validate_pmid(pmid):
            logger.warning(f"Invalid PMID format: {pmid}, skipping")
            return None
        
        # Extract title with cleaning
        title = ""
        if "Title" in record:
            title = clean_text(record["Title"])
        elif "ArticleTitle" in record:
            title = clean_text(record["ArticleTitle"])
        
        if not title or len(title) < 10:
            logger.warning(f"PMID {pmid}: Title too short or missing, skipping")
            return None
        
        # Extract abstract with validation
        abstract = ""
        if "Abstract" in record:
            if isinstance(record["Abstract"], dict):
                abstract_text = record["Abstract"].get("AbstractText", "")
            else:
                abstract_text = record["Abstract"]
            
            if isinstance(abstract_text, list):
                abstract = " ".join(str(part) for part in abstract_text if part)
            else:
                abstract = str(abstract_text) if abstract_text else ""
            
            abstract = clean_text(abstract)
        
        # Skip if abstract is too short (likely low-quality record)
        if len(abstract) < int(os.getenv('PUBMEDRAG_MIN_ABSTRACT_LENGTH', '50')):
            logger.warning(f"PMID {pmid}: Abstract too short ({len(abstract)} chars), skipping")
            return None
        
        # Extract DOI with validation
        doi = ""
        if "DOI" in record:
            doi = clean_text(record["DOI"])
        
        # Extract and format authors
        authors = ""
        if "AuthorList" in record and record["AuthorList"]:
            author_names = []
            for author in record["AuthorList"][:6]:  # Limit to first 6 authors
                if isinstance(author, dict):
                    last_name = author.get("LastName", "")
                    first_name = author.get("ForeName", "")
                    if last_name:
                        if first_name:
                            author_names.append(f"{last_name} {first_name[0]}")
                        else:
                            author_names.append(last_name)
                elif isinstance(author, str):
                    author_names.append(author)
            
            if author_names:
                if len(record["AuthorList"]) > 6:
                    authors = ", ".join(author_names) + ", et al."
                else:
                    authors = ", ".join(author_names)
        
        # Extract journal information
        journal = ""
        if "FullJournalName" in record:
            journal = clean_text(record["FullJournalName"])
        elif "Journal" in record:
            journal_info = record["Journal"]
            if isinstance(journal_info, dict):
                journal = clean_text(journal_info.get("Title", ""))
            else:
                journal = clean_text(str(journal_info))
        
        # Extract publication date with validation
        pub_date = ""
        if "PubDate" in record:
            date_info = record["PubDate"]
            if isinstance(date_info, dict):
                year = date_info.get("Year", "")
                month = date_info.get("Month", "")
                day = date_info.get("Day", "")
                
                if year:
                    pub_date = str(year)
                    if month:
                        pub_date += f" {month}"
                        if day:
                            pub_date += f" {day}"
            else:
                pub_date = clean_text(str(date_info))
        
        # Quality control: Check publication year
        current_year = datetime.now().year
        max_years_back = int(os.getenv('PUBMEDRAG_MAX_SEARCH_YEARS', '20'))
        
        if pub_date:
            try:
                year_match = re.search(r'\b(19|20)\d{2}\b', pub_date)
                if year_match:
                    pub_year = int(year_match.group())
                    if current_year - pub_year > max_years_back:
                        logger.info(f"PMID {pmid}: Article too old ({pub_year}), skipping")
                        return None
            except ValueError:
                pass  # If year parsing fails, continue anyway
        
        # Quality control: Exclude certain publication types if configured
        exclude_letters = os.getenv('PUBMEDRAG_EXCLUDE_LETTERS', 'false').lower() == 'true'
        exclude_editorials = os.getenv('PUBMEDRAG_EXCLUDE_EDITORIALS', 'false').lower() == 'true'
        
        publication_types = record.get("PublicationTypeList", [])
        if isinstance(publication_types, list):
            type_strings = [str(pt).lower() for pt in publication_types]
            
            if exclude_letters and any('letter' in t for t in type_strings):
                logger.info(f"PMID {pmid}: Excluding letter to editor")
                return None
                
            if exclude_editorials and any('editorial' in t for t in type_strings):
                logger.info(f"PMID {pmid}: Excluding editorial")
                return None
        
        # Create article object
        article = PubMedArticle(
            pmid=pmid,  # Already validated and cleaned
            title=title,
            abstract=abstract,
            doi=doi,
            authors=authors,
            journal=journal,
            pub_date=pub_date
        )
        
        logger.debug(f"✅ Successfully parsed PMID: {pmid}, Title: {title[:50]}...")
        return article
        
    except Exception as e:
        logger.error(f"Error parsing PubMed record: {e}")
        return None


def parse_pubmed_results(results: List[Dict[str, Any]]) -> List[PubMedArticle]:
    """Parse PubMed search results with enhanced validation."""
    articles = []
    
    logger.info(f"📋 Parsing {len(results)} PubMed records...")
    
    for i, record in enumerate(results):
        try:
            article = parse_pubmed_xml_record(record)
            if article:
                articles.append(article)
                if (i + 1) % 50 == 0:  # Progress feedback
                    logger.info(f"📄 Processed {i + 1}/{len(results)} records, {len(articles)} valid articles")
        except Exception as e:
            logger.error(f"Error processing record {i}: {e}")
            continue
    
    logger.info(f"📋 Final result: {len(articles)} valid articles from {len(results)} records")
    return articles


def fetch_pubmed_articles(email: str, search_term: str, ncbi_api_key: Optional[str] = None,
                         db: str = "pubmed", retmax: int = 50) -> List[PubMedArticle]:
    """Fetch articles for a single search term from PubMed."""
    if not email or "@" not in email:
        raise ValueError("Please provide a valid email address")
    
    Entrez.email = email
    if ncbi_api_key:
        Entrez.api_key = ncbi_api_key
    
    logger.info(f"🔍 Searching PubMed for: '{search_term}'")
    
    try:
        # Search for articles
        with Entrez.esearch(db=db, term=search_term, retmax=retmax, sort="relevance") as handle:
            search_record = Entrez.read(handle)
        
        id_list = search_record["IdList"]
        if not id_list:
            logger.warning(f"⚠️ No articles found for '{search_term}'")
            return []
        
        logger.info(f"📄 Found {len(id_list)} articles")
        
        # Fetch detailed records in text format
        with Entrez.efetch(db=db, id=id_list, rettype="abstract", retmode="text") as handle:
            records_text = handle.read()
        
        # Parse records using text parser
        articles = parse_pubmed_text_record(records_text)
        logger.info(f"✅ Successfully parsed {len(articles)} articles with abstracts")
        return articles
        
    except Exception as e:
        logger.error(f"Error fetching PubMed articles: {e}")
        return []


def chunk_abstracts(articles: List[PubMedArticle], chunk_size: int = 500, 
                   chunk_overlap: int = 50) -> Tuple[List[str], List[Dict[str, str]]]:
    """Chunk article abstracts while preserving metadata."""
    chunks = []
    metadata = []
    
    for article in articles:
        abstract_text = article.abstract
        
        if len(abstract_text) <= chunk_size:
            # Keep small abstracts as single chunks
            chunks.append(abstract_text)
            metadata.append(article.to_dict())
        else:
            # Split larger abstracts
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=[". ", "! ", "? ", "\n", " ", ""]
            )
            
            docs = splitter.create_documents([abstract_text])
            
            for i, doc in enumerate(docs):
                if doc.page_content.strip():
                    chunks.append(doc.page_content.strip())
                    # Add chunk index to metadata
                    chunk_metadata = article.to_dict()
                    chunk_metadata['chunk_index'] = i
                    chunk_metadata['total_chunks'] = len(docs)
                    metadata.append(chunk_metadata)
    
    logger.info(f"📝 Created {len(chunks)} text chunks from {len(articles)} articles")
    return chunks, metadata


class ChromaDBManager:
    """Manage ChromaDB collections for vector storage."""

    def __init__(self, collection_name: str, db_path: str = "./chroma_db"):
        self.collection_name = collection_name
        self.db_path = db_path
        
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False),
            tenant=DEFAULT_TENANT,
            database=DEFAULT_DATABASE,
        )
        logger.info(f"🗄️ ChromaDB initialized at: {db_path}")

    def get_or_create_collection(self):
        """Get or create a collection."""
        return self.client.get_or_create_collection(name=self.collection_name)

    def add_documents(self, chunks: List[str], embeddings: List[List[float]], 
                     metadata: List[Dict[str, str]]):
        """Add documents with metadata to the collection."""
        collection = self.get_or_create_collection()
        ids = [str(uuid.uuid4()) for _ in chunks]
        
        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadata
        )
        logger.info(f"✅ Added {len(chunks)} documents to ChromaDB")

    def query(self, query_text: str, query_embedding: List[float], k: int = 10):
        """Query the collection for relevant documents."""
        collection = self.get_or_create_collection()
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            include=["documents", "distances", "metadatas"],
        )
        logger.info(f"🔍 Retrieved {len(result['documents'][0])} relevant chunks")
        return result

    def delete_collection(self):
        """Delete the collection."""
        self.client.delete_collection(self.collection_name)
        logger.info(f"🗑️ Deleted collection: {self.collection_name}")


class QuestionDrivenRAG:
    """Question-driven PubMed RAG system."""

    def __init__(self, 
                 email: str,
                 llm_api_key: str,
                 llm_base_url: str = "https://api.deepseek.com/v1",
                 llm_model: str = "deepseek-chat",
                 ncbi_api_key: Optional[str] = None,
                 embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
                 temperature: float = 0.3,
                 initial_search_terms_range: Tuple[int, int] = (10, 30),
                 followup_search_terms_range: Tuple[int, int] = (5, 30)):
        
        self.email = email
        self.ncbi_api_key = ncbi_api_key
        self.llm_model = llm_model
        self.temperature = temperature
        self.initial_search_terms_range = initial_search_terms_range
        self.followup_search_terms_range = followup_search_terms_range
        
        # Initialize search history
        self.session_id = str(uuid.uuid4())
        self.search_history = SearchHistory(
            session_id=self.session_id,
            collection_name=f"pubmed_rag_{self.session_id}"
        )
        
        # Initialize embedding model
        logger.info(f"🧠 Loading embedding model: {embedding_model}")
        self.embedder = SentenceTransformer(embedding_model)
        
        # Initialize LLM client
        self.llm_client = OpenAI(api_key=llm_api_key, base_url=llm_base_url)
        
        # Initialize ChromaDB
        self.chroma_mgr = ChromaDBManager(self.search_history.collection_name)
        
        logger.info(f"✅ QuestionDrivenRAG initialized with session: {self.session_id}")

    def generate_search_terms(self, question: str, is_initial: bool = True) -> List[str]:
        """Generate PubMed search terms based on the question using LLM."""
        if is_initial:
            min_terms, max_terms = self.initial_search_terms_range
            context = "This is the first question in a new research session."
        else:
            min_terms, max_terms = self.followup_search_terms_range
            context = "This is a follow-up question in an ongoing research session."
        
        prompt = f"""
You are a biomedical literature search specialist.

Context: {context}

Question:
"{question}"

Task:
Generate between {min_terms} and {max_terms} PubMed search terms that can be used to find relevant literature for this question. You should generate the optimal number of terms within this range based on the complexity and scope of the question.

INSTRUCTIONS (follow carefully):
1. Identify key biomedical concepts — such as gene/protein names, drug names, clinical terms, or pathways.
2. If the question contains abbreviations (e.g., THBS2, P53, VEGF), use them exactly as written.
3. Include common synonyms or alternative names where appropriate.
4. Use [Title/Abstract] field tags for all search terms.
5. Combine concepts using Boolean operators (AND / OR) to improve precision.
6. Each line should represent a distinct way to search — exploring different aspects of the question.
7. Generate between {min_terms} and {max_terms} terms. Choose the optimal number based on question complexity.
8. Do NOT include numbering, explanations, or extra text.

Example (for: "Does THBS2 cause immunotherapy resistance?"):
THBS2[Title/Abstract] AND immunotherapy resistance[Title/Abstract]
thrombospondin-2[Title/Abstract] AND immune checkpoint inhibitor[Title/Abstract]
THBS2[Title/Abstract] AND cancer immunotherapy[Title/Abstract]
thrombospondin 2[Title/Abstract] AND treatment resistance[Title/Abstract]
THBS2[Title/Abstract] AND tumor immunity[Title/Abstract]
THBS2[Title/Abstract] AND PD-1[Title/Abstract]
THBS2[Title/Abstract] AND PD-L1[Title/Abstract]
thrombospondin-2[Title/Abstract] AND CAR-T[Title/Abstract]
THBS2[Title/Abstract] AND immune evasion[Title/Abstract]
thrombospondin 2[Title/Abstract] AND T cell exhaustion[Title/Abstract]

Now generate the optimal number of PubMed search terms (between {min_terms} and {max_terms}):
"""
        response = self.llm_client.chat.completions.create(
            model=self.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Lower temperature for more consistent results
            max_tokens=1500
        )
        
        terms_text = response.choices[0].message.content.strip()
        search_terms = [term.strip() for term in terms_text.split('\n') if term.strip()]
        
        # Ensure we're within the specified range
        if len(search_terms) < min_terms:
            logger.warning(f"⚠️ Generated only {len(search_terms)} terms, minimum is {min_terms}")
        elif len(search_terms) > max_terms:
            search_terms = search_terms[:max_terms]
            logger.info(f"🔄 Trimmed to {max_terms} terms (maximum allowed)")
        
        logger.info(f"✅ Generated {len(search_terms)} search terms")
        for i, term in enumerate(search_terms, 1):
            logger.info(f"   {i}. {term}")
        
        return search_terms

    def generate_session_topic(self, questions: List[str]) -> str:
        """Generate a one-sentence topic description for the session."""
        if not questions:
            return "New research session"
        
        # Use the first few questions to generate topic
        questions_text = "\n".join(questions[:3])  # Use first 3 questions
        
        prompt = f"""
Based on these research questions, generate a single sentence (maximum 15 words) that describes the main research topic:

Questions:
{questions_text}

Generate a concise topic description (one sentence, maximum 15 words):
"""
        
        response = self.llm_client.chat.completions.create(
            model=self.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=50
        )
        
        topic = response.choices[0].message.content.strip()
        # Clean up the topic
        topic = topic.strip('."')
        if len(topic.split()) > 15:
            topic = ' '.join(topic.split()[:15])
        
        return topic

    def check_need_new_search(self, question: str) -> Tuple[bool, List[str]]:
        """Use LLM to determine if new searches are needed for the question."""
        if not self.search_history.queries:
            # First question always needs search
            return True, []
        
        # Prepare search history for LLM
        history_context = {
            "total_articles": len(self.search_history.indexed_pmids),
            "previous_questions": [q["question"] for q in self.search_history.queries[-3:]],
            "previous_search_terms": list(self.search_history.all_search_terms)[-15:]  # Last 15 terms
        }
        
        min_terms, max_terms = self.followup_search_terms_range
        
        prompt = f"""
Analyze whether additional PubMed searches are needed for this new question based on existing search history.

EXISTING DATA:
- Total indexed articles: {history_context['total_articles']}
- Recent questions: {json.dumps(history_context['previous_questions'], indent=2)}
- Previous search terms: {json.dumps(history_context['previous_search_terms'], indent=2)}

NEW QUESTION: "{question}"

CRITICAL: Extract key medical terms, gene/protein names, drug names from the NEW QUESTION.
If the question mentions specific terms (like THBS2, P53, VEGF, specific drugs, etc.) that are NOT covered in previous search terms, you MUST search for them.

Determine if additional searches are needed. If yes, generate {min_terms}-{max_terms} NEW search terms that focus on the specific entities mentioned in the question.

MUST respond in exact JSON format:
{{
    "need_new_search": true/false,
    "reasoning": "brief explanation focusing on specific terms that need searching",
    "new_search_terms": [
        "specific_term[Title/Abstract] AND relevant_concept[Title/Abstract]",
        "synonym[Title/Abstract] AND related_aspect[Title/Abstract]"
    ]
}}
"""

        response = self.llm_client.chat.completions.create(
            model=self.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Lower temperature for consistency
            max_tokens=1200
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse LLM JSON response
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if not json_match:
            logger.warning("Failed to parse LLM JSON response, defaulting to new search")
            return True, []
            
        try:
            result = json.loads(json_match.group())
            need_search = result["need_new_search"]
            new_terms = result["new_search_terms"]
            reasoning = result.get("reasoning", "")
            
            # Ensure terms are within range
            if need_search and len(new_terms) < min_terms:
                logger.warning(f"⚠️ LLM generated only {len(new_terms)} terms, minimum is {min_terms}")
            elif need_search and len(new_terms) > max_terms:
                new_terms = new_terms[:max_terms]
                logger.info(f"🔄 Trimmed to {max_terms} terms (maximum allowed)")
            
            logger.info(f"📊 Search decision: need_new={need_search}, new_terms={len(new_terms)}")
            logger.info(f"💭 Reasoning: {reasoning}")
            
            return need_search, new_terms
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON, defaulting to new search")
            return True, []

    def search_and_index(self, search_terms: List[str], retmax_per_term: int = 30) -> List[str]:
        """Search PubMed and index new articles."""
        new_pmids = []
        all_articles = []
        
        for term in search_terms:
            logger.info(f"🔍 Searching: {term}")
            articles = fetch_pubmed_articles(
                self.email, 
                term, 
                self.ncbi_api_key, 
                retmax=retmax_per_term
            )
            
            # Filter out already indexed articles
            new_articles = []
            for article in articles:
                if article.pmid not in self.search_history.indexed_pmids:
                    new_articles.append(article)
                    new_pmids.append(article.pmid)
            
            if new_articles:
                all_articles.extend(new_articles)
                logger.info(f"✅ Found {len(new_articles)} new articles")
            
            time.sleep(0.5)  # Rate limiting
        
        # Index new articles
        if all_articles:
            logger.info(f"📚 Indexing {len(all_articles)} new articles...")
            
            # Chunk abstracts
            chunks, metadata = chunk_abstracts(all_articles)
            
            # Generate embeddings
            logger.info("🧠 Generating embeddings...")
            embeddings = self.embedder.encode(chunks, show_progress_bar=True)
            
            # Add to ChromaDB
            self.chroma_mgr.add_documents(chunks, embeddings.tolist(), metadata)
            
            logger.info(f"✅ Successfully indexed {len(all_articles)} articles")
        
        return new_pmids

    def answer_question(self, question: str, k: int = 10, max_tokens: int = 10000) -> Dict[str, Any]:
        """Answer a question using the indexed literature."""
        is_first_question = len(self.search_history.queries) == 0
        
        # Check if we need new searches
        need_search, new_terms = self.check_need_new_search(question)
        
        # If first question or need new search
        if is_first_question or need_search:
            if not new_terms:
                # Generate search terms from question
                new_terms = self.generate_search_terms(question, is_initial=is_first_question)
            
            # Search and index
            new_pmids = self.search_and_index(new_terms, retmax_per_term=30)
            
            # Update search history
            self.search_history.add_query(question, new_terms, new_pmids)
            
            # Generate topic for the session after first question
            if is_first_question:
                self.search_history.topic = self.generate_session_topic([question])
        
        # Generate query embedding
        query_embedding = self.embedder.encode([question])[0].tolist()
        
        # Search ChromaDB
        retrieval = self.chroma_mgr.query(question, query_embedding, k=k)
        
        if not retrieval["documents"][0]:
            return {
                "answer": "I couldn't find relevant information in the medical literature to answer your question. Try rephrasing or asking about a different aspect.",
                "citations": [],
                "search_performed": need_search,
                "new_articles": 0
            }
        
        # Log retrieval info
        logger.info(f"🔍 Retrieved {len(retrieval['documents'][0])} chunks, will deduplicate by article")
        
        # Prepare context from retrieved chunks with proper citation numbering
        context_chunks = []
        citations_dict = {}  # Track unique citations by PMID
        pmid_chunks = {}     # Track chunks per PMID to avoid over-representation
        pmid_to_citation_num = {}  # Map PMID to citation number
        
        # First pass: collect unique citations and assign numbers
        citation_counter = 1
        for i, (chunk, metadata) in enumerate(zip(retrieval["documents"][0], retrieval["metadatas"][0])):
            pmid = metadata.get("pmid", "")
            if pmid and pmid not in citations_dict:
                citations_dict[pmid] = {
                    "pmid": pmid,  # Keep original PMID
                    "title": metadata.get("title", ""),
                    "doi": metadata.get("doi", ""),
                    "authors": metadata.get("authors", ""),
                    "journal": metadata.get("journal", ""),
                    "pub_date": metadata.get("pub_date", ""),
                    "number": citation_counter
                }
                pmid_to_citation_num[pmid] = citation_counter
                citation_counter += 1
        
        # Second pass: build context with correct citation numbers
        for i, (chunk, metadata) in enumerate(zip(retrieval["documents"][0], retrieval["metadatas"][0])):
            pmid = metadata.get("pmid", "")
            
            # Limit chunks per article (max 2 chunks per article to avoid over-weighting)
            if pmid:
                if pmid not in pmid_chunks:
                    pmid_chunks[pmid] = []
                
                if len(pmid_chunks[pmid]) < 2:  # Max 2 chunks per article
                    citation_num = pmid_to_citation_num.get(pmid, len(context_chunks)+1)
                    context_chunks.append(f"[{citation_num}] {chunk}")
                    pmid_chunks[pmid].append(chunk)
                else:
                    continue  # Skip additional chunks from same article
            else:
                # No PMID, include anyway but with generic numbering
                context_chunks.append(f"[{len(context_chunks)+1}] {chunk}")
        
        context = "\n\n".join(context_chunks)
        
        # Log context statistics
        unique_articles = len(citations_dict)
        total_chunks = len(context_chunks)
        logger.info(f"📚 Using {total_chunks} chunks from {unique_articles} unique articles for context")
        
        # Generate answer using LLM
        prompt = f"""
You are a professional biomedical research assistant.

Your task is to answer the following question using both:
- The provided scientific literature (PubMed abstracts)
- Your own medical knowledge if necessary

Context from PubMed abstracts:
{context}

Question:
{question}

Answering Instructions:
1. Provide a clear, accurate, evidence-based response.
2. Prioritize using information from the abstracts above.
3. If helpful, supplement with reliable medical knowledge you already know.
4. Cite references from the provided abstracts using [1], [2], etc., based on their order.
5. If the literature is insufficient to fully answer the question, clearly say so.
6. Structure your answer with clear bullet points or short paragraphs.
7. Do NOT start your response with "Answer:" - start directly with your response.

Provide your response:
"""

        # Generate answer using LLM
        logger.info("🤖 Generating answer using LLM...")
        
        response = self.llm_client.chat.completions.create(
            model=self.llm_model,
            messages=[
                {
                    "role": "system", 
                    "content": """You are a medical research expert. Based on the provided literature context, answer the user's question accurately and comprehensively. 

CITATION RULES:
1. Use ONLY the numbered citations provided in the context [1], [2], [3], etc.
2. Cite sources for ALL factual claims 
3. Use multiple citations for broad claims: [1,2,3]
4. Place citations immediately after the relevant statement
5. DO NOT create new citation numbers
6. If information isn't in the provided context, state this clearly

FORMAT:
- Use clear headings and bullet points
- Be specific about mechanisms, pathways, and findings
- Distinguish between different types of studies when relevant
- Acknowledge limitations or conflicting evidence if present"""
                },
                {
                    "role": "user", 
                    "content": f"""Question: {question}

Literature Context:
{context}

Please provide a comprehensive answer based on the literature provided."""
                }
            ],
            temperature=self.temperature,
            max_tokens=int(os.getenv('PUBMEDRAG_MAX_TOKENS', '4000'))
        )
        
        answer = response.choices[0].message.content.strip()
        
        # Extract actually cited references from the answer
        logger.info("🔍 Extracting cited references from answer...")
        cited_numbers = set()
        
        # Find all citation patterns: [1], [2], [1,2], [1-3], etc.
        citation_patterns = [
            r'\[(\d+)\]',                    # [1]
            r'\[(\d+),\s*(\d+)\]',          # [1,2]  
            r'\[(\d+),\s*(\d+),\s*(\d+)\]', # [1,2,3]
            r'\[(\d+)-(\d+)\]'              # [1-3]
        ]
        
        for pattern in citation_patterns:
            matches = re.findall(pattern, answer)
            for match in matches:
                if isinstance(match, tuple):
                    for num in match:
                        if num.isdigit():
                            cited_numbers.add(int(num))
                elif match.isdigit():
                    cited_numbers.add(int(match))
        
        # Handle range citations like [1-3]
        range_matches = re.findall(r'\[(\d+)-(\d+)\]', answer)
        for start, end in range_matches:
            for num in range(int(start), int(end) + 1):
                cited_numbers.add(num)
        
        logger.info(f"📚 Found citations in answer: {sorted(cited_numbers)}")
        
        # Filter citations to only include those actually cited
        cited_citations = []
        citations_by_number = {citation["number"]: citation for citation in citations_dict.values()}
        
        for num in sorted(cited_numbers):
            if num in citations_by_number:
                citation = citations_by_number[num]
                # Validate PMID format before including
                pmid = citation.get('pmid', '')
                if validate_pmid(pmid):
                    cited_citations.append(citation)
                else:
                    logger.warning(f"Invalid PMID in citation {num}: {pmid}")
            else:
                logger.warning(f"Citation [{num}] referenced in answer but not found in context")
        
        logger.info(f"✅ Validated {len(cited_citations)} citations for final output")
        
        return {
            "answer": answer,
            "citations": cited_citations,  # Only actually cited and validated references
            "search_performed": need_search,
            "new_articles": len(self.search_history.indexed_pmids),
            "total_articles": len(self.search_history.indexed_pmids)
        }

    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information."""
        return {
            "session_id": self.session_id,
            "topic": self.search_history.topic,
            "total_questions": len(self.search_history.queries),
            "total_articles": len(self.search_history.indexed_pmids),
            "total_search_terms": len(self.search_history.all_search_terms),
            "created_at": self.search_history.created_at.isoformat()
        }

    def close(self):
        """Clean up resources."""
        self.chroma_mgr.delete_collection()
        logger.info("✅ Session closed and resources cleaned up")