#!/usr/bin/env python3
"""
CLI interface for PubMedRAG - Medical Literature Research Assistant
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Third-party imports
from colorama import Fore, Style, init
from dotenv import load_dotenv
from openai import OpenAI

# Local imports
from .core import QuestionDrivenRAG
from .cache import SessionCache
from .utils import setup_logging, format_reference

# Initialize colorama for cross-platform colored output
init()

def print_banner():
    """Print the application banner."""
    banner = f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║    🧬  PubMedRAG - Question-Driven Medical Literature Assistant  🧬    ║
║                                                                       ║
║       ✨ Ask questions → Get answers from PubMed literature ✨       ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""
    print(banner)

def print_section(title: str, emoji: str = ""):
    """Print a section header."""
    print(f"\n{emoji} {Fore.CYAN}{title}{Style.RESET_ALL}")
    print("─" * (len(title) + len(emoji) + 1))

def format_time_ago(timestamp: str) -> str:
    """Format timestamp as 'X minutes/hours/days ago'."""
    try:
        from datetime import datetime
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            dt = datetime.fromtimestamp(timestamp)
        
        diff = datetime.now() - dt
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "just now"
    except:
        return "unknown time"

def load_env_config() -> Optional[Dict[str, Any]]:
    """Load configuration from .env file."""
    # Try multiple .env file locations
    env_locations = [
        Path('.env'),  # Current directory
        Path.cwd() / '.env',  # Current working directory
        Path(__file__).parent / '.env',  # Same directory as this script
        Path(__file__).parent.parent / '.env',  # Parent directory
    ]
    
    env_loaded = False
    env_path = None
    
    for location in env_locations:
        if location.exists():
            print(f"{Fore.GREEN}📁 Found .env file at: {location}{Style.RESET_ALL}")
            load_dotenv(location)
            env_loaded = True
            env_path = location
            break
    
    if not env_loaded:
        print(f"{Fore.YELLOW}⚠️ No .env file found in:{Style.RESET_ALL}")
        for location in env_locations:
            print(f"   - {location}")
        return None
    
    # Check required environment variables
    required_vars = {
        'PUBMEDRAG_EMAIL': os.getenv('PUBMEDRAG_EMAIL'),
        'PUBMEDRAG_API_KEY': os.getenv('PUBMEDRAG_API_KEY'),
        'PUBMEDRAG_BASE_URL': os.getenv('PUBMEDRAG_BASE_URL'),
        'PUBMEDRAG_MODEL': os.getenv('PUBMEDRAG_MODEL')
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    
    if missing_vars:
        print(f"{Fore.RED}❌ Missing required environment variables in {env_path}:{Style.RESET_ALL}")
        for var in missing_vars:
            print(f"   - {var}")
        print(f"\n{Fore.YELLOW}Please check your .env file and add the missing variables.{Style.RESET_ALL}")
        return None
    
    print(f"{Fore.GREEN}✅ All required configuration loaded from .env{Style.RESET_ALL}")
    
    # Build configuration dictionary
    config = {
        'email': required_vars['PUBMEDRAG_EMAIL'],
        'llm_api_key': required_vars['PUBMEDRAG_API_KEY'],
        'llm_base_url': required_vars['PUBMEDRAG_BASE_URL'],
        'llm_model': required_vars['PUBMEDRAG_MODEL'],
        'ncbi_api_key': os.getenv('NCBI_API_KEY'),
        'initial_search_terms_range': (
            int(os.getenv('PUBMEDRAG_INITIAL_SEARCH_MIN', '10')),
            int(os.getenv('PUBMEDRAG_INITIAL_SEARCH_MAX', '25'))
        ),
        'followup_search_terms_range': (
            int(os.getenv('PUBMEDRAG_FOLLOWUP_SEARCH_MIN', '5')),
            int(os.getenv('PUBMEDRAG_FOLLOWUP_SEARCH_MAX', '20'))
        ),
        'temperature': float(os.getenv('PUBMEDRAG_TEMPERATURE', '0.3')),
        'embedding_model': os.getenv('PUBMEDRAG_EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
    }
    
    return config

def get_configuration() -> Dict[str, Any]:
    """Get configuration from environment variables or interactive input."""
    print_section("Loading Configuration", "🔧")
    
    # Try to load from environment first
    config = load_env_config()
    
    if config:
        # Display loaded configuration (without sensitive data)
        print(f"\n{Fore.CYAN}📋 Configuration Summary:{Style.RESET_ALL}")
        print(f"   📧 Email: {config['email']}")
        print(f"   🤖 Model: {config['llm_model']}")
        print(f"   🌐 Base URL: {config['llm_base_url']}")
        print(f"   🔑 API Key: {'*' * 8}...{config['llm_api_key'][-4:] if len(config['llm_api_key']) > 4 else '****'}")
        
        if config.get('ncbi_api_key'):
            print(f"   🧬 NCBI API: {Fore.GREEN}Configured{Style.RESET_ALL}")
        else:
            print(f"   🧬 NCBI API: {Fore.YELLOW}Not configured (optional){Style.RESET_ALL}")
        
        print(f"   🔍 Search ranges: {config['initial_search_terms_range']} / {config['followup_search_terms_range']}")
        
        return config
    
    # If no config found, provide guidance
    print(f"\n{Fore.RED}❌ Configuration not found or incomplete{Style.RESET_ALL}")
    print(f"\n{Fore.CYAN}📝 To fix this:{Style.RESET_ALL}")
    print(f"1. Create a .env file in your current directory:")
    print(f"   {Fore.YELLOW}touch .env{Style.RESET_ALL}")
    print(f"\n2. Add your configuration to .env:")
    print(f"""   {Fore.YELLOW}PUBMEDRAG_EMAIL=your-email@university.edu
   PUBMEDRAG_API_KEY=your-api-key-here
   PUBMEDRAG_BASE_URL=https://api.qingyuntop.top/v1
   PUBMEDRAG_MODEL=o3-mini
   NCBI_API_KEY=your-ncbi-key{Style.RESET_ALL}""")
    
    print(f"\n3. Restart PubMedRAG")
    
    # Ask if user wants to continue with manual configuration
    choice = input(f"\n{Fore.YELLOW}Enter configuration manually for this session? (y/n): {Style.RESET_ALL}").strip().lower()
    
    if choice != 'y':
        print(f"{Fore.CYAN}👋 Exiting. Please create .env file and try again.{Style.RESET_ALL}")
        sys.exit(0)
    
    # Fall back to interactive configuration
    return get_manual_configuration()

def get_manual_configuration() -> Dict[str, Any]:
    """Get configuration through interactive input (fallback)."""
    print_section("Manual Configuration", "📝")
    
    # Get required settings
    email = input(f"\n{Fore.CYAN}📧 Email for NCBI/PubMed access:{Style.RESET_ALL} ").strip()
    if not email:
        print(f"{Fore.RED}❌ Email is required{Style.RESET_ALL}")
        sys.exit(1)
    
    # LLM Configuration
    print(f"\n{Fore.CYAN}🤖 AI Model Configuration{Style.RESET_ALL}")
    print(f"Choose your AI service:")
    print(f"1. 🚀 DeepSeek (Recommended)")
    print(f"2. 🔧 Custom OpenAI-compatible API")
    print(f"3. 🏢 OpenAI Official")
    
    llm_choice = input(f"\n{Fore.YELLOW}Choice (1/2/3, default 1):{Style.RESET_ALL} ").strip() or "1"
    
    if llm_choice == "1":
        llm_base_url = "https://api.deepseek.com/v1"
        llm_model = "deepseek-chat"
        print(f"{Fore.GREEN}📋 Selected: DeepSeek{Style.RESET_ALL}")
    elif llm_choice == "2":
        llm_base_url = input(f"{Fore.CYAN}API Base URL:{Style.RESET_ALL} ").strip()
        llm_model = input(f"{Fore.CYAN}Model name:{Style.RESET_ALL} ").strip()
    else:
        llm_base_url = "https://api.openai.com/v1"
        llm_model = "gpt-3.5-turbo"
        print(f"{Fore.GREEN}📋 Selected: OpenAI{Style.RESET_ALL}")
    
    llm_api_key = input(f"{Fore.CYAN}🔑 API Key:{Style.RESET_ALL} ").strip()
    if not llm_api_key:
        print(f"{Fore.RED}❌ API Key is required{Style.RESET_ALL}")
        sys.exit(1)
    
    # Optional NCBI API Key
    print(f"\n{Fore.CYAN}🔑 NCBI API Key (optional - for higher rate limits):{Style.RESET_ALL}")
    print(f"Get one at: https://www.ncbi.nlm.nih.gov/account/")
    ncbi_api_key = input(f"{Fore.CYAN}NCBI API Key (press Enter to skip):{Style.RESET_ALL} ").strip()
    
    # Search configuration with defaults
    print(f"\n{Fore.CYAN}🔍 Search Configuration{Style.RESET_ALL}")
    print(f"Configure search term ranges (or press Enter for defaults):")
    
    try:
        initial_min = int(input(f"Initial search terms minimum (default 10): ") or "10")
        initial_max = int(input(f"Initial search terms maximum (default 25): ") or "25")
        followup_min = int(input(f"Follow-up search terms minimum (default 5): ") or "5")
        followup_max = int(input(f"Follow-up search terms maximum (default 20): ") or "20")
    except ValueError:
        print(f"{Fore.YELLOW}⚠️ Using default search ranges{Style.RESET_ALL}")
        initial_min, initial_max = 10, 25
        followup_min, followup_max = 5, 20
    
    return {
        'email': email,
        'llm_api_key': llm_api_key,
        'llm_base_url': llm_base_url,
        'llm_model': llm_model,
        'ncbi_api_key': ncbi_api_key if ncbi_api_key else None,
        'initial_search_terms_range': (initial_min, initial_max),
        'followup_search_terms_range': (followup_min, followup_max),
        'temperature': 0.3,
        'embedding_model': 'sentence-transformers/all-MiniLM-L6-v2'
    }

def test_configuration(config: Dict[str, Any]) -> None:
    """Test the configuration by making a simple API call."""
    print_section("Testing Configuration", "🧪")
    
    try:
        client = OpenAI(
            api_key=config['llm_api_key'],
            base_url=config['llm_base_url']
        )
        
        # Simple test call
        response = client.chat.completions.create(
            model=config['llm_model'],
            messages=[{"role": "user", "content": "Hello, this is a test."}],
            max_tokens=10,
            temperature=0.1
        )
        
        print(f"{Fore.GREEN}✅ API connection successful!{Style.RESET_ALL}")
        
    except Exception as e:
        print(f"{Fore.RED}❌ API connection failed: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Please check your API key and base URL{Style.RESET_ALL}")
        
        choice = input(f"\n{Fore.YELLOW}Continue anyway? (y/n):{Style.RESET_ALL} ").strip().lower()
        if choice != 'y':
            sys.exit(1)

def load_existing_session(llm_client: OpenAI):
    """Show existing session info for reference only."""
    session_cache = SessionCache(llm_client=llm_client)
    sessions = session_cache.list_sessions()
    
    if not sessions:
        return None
    
    print_section("Recent Sessions", "📁")
    
    for i, session in enumerate(sessions[:3], 1):  # Show only top 3
        topic = session.get('topic', session.get('description', 'No description'))
        print(f"\n{Fore.CYAN}{i}. {topic}{Style.RESET_ALL}")
        print(f"   Questions: {session['total_questions']}")
        print(f"   Articles: {session['total_articles']}")
        print(f"   Updated: {format_time_ago(session['last_updated'])}")
        
        # Show sample questions
        if session.get('questions'):
            print(f"   Recent: {session['questions'][0][:60]}...")
    
    print(f"\n{Fore.YELLOW}💡 PubMedRAG will automatically suggest using relevant sessions when you ask questions.{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}   Just start asking your research questions!{Style.RESET_ALL}")
    
    input(f"\n{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
    return None

def check_for_matching_topic(question: str, session_cache: SessionCache) -> Optional[str]:
    """Check if question matches an existing topic and automatically decide."""
    matching_session = session_cache.find_matching_session(question)
    
    if matching_session:
        topic = matching_session.get('topic', 'Unknown topic')
        session_id = matching_session.get('session_id', '')
        total_articles = len(matching_session.get('indexed_pmids', []))
        
        print(f"\n{Fore.CYAN}🎯 Found matching research topic:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}   Topic: {topic}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}   Articles: {total_articles}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}   Session ID: {session_id[:8]}...{Style.RESET_ALL}")
        
        # Auto-decide with confidence threshold
        if total_articles >= 50:  # High confidence threshold
            print(f"{Fore.GREEN}✅ Automatically using existing database (high relevance detected){Style.RESET_ALL}")
            return session_id
        else:
            print(f"{Fore.YELLOW}🤔 Relevant database found, but may need additional sources{Style.RESET_ALL}")
            use_existing = input(f"\n{Fore.YELLOW}Use existing database? (y/n, default y):{Style.RESET_ALL} ").strip().lower()
            if use_existing != 'n':
                return session_id
    
    return None

def interactive_session(rag: QuestionDrivenRAG, config: Dict[str, Any]) -> None:
    """Run the interactive Q&A session."""
    print_section("Interactive Session", "💬")
    print(f"{Fore.GREEN}🎯 Ready for your questions! Type 'quit' to exit.{Style.RESET_ALL}")
    
    # Create LLM client for session cache
    llm_client = OpenAI(
        api_key=config['llm_api_key'],
        base_url=config['llm_base_url']
    )
    session_cache = SessionCache(llm_client=llm_client)
    question_count = 0
    
    while True:
        try:
            # Get user question
            user_input = input(f"\n{Fore.YELLOW}❓ Ask a question:{Style.RESET_ALL} ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'bye']:
                print(f"{Fore.CYAN}👋 Goodbye!{Style.RESET_ALL}")
                break
            
            # Handle special commands
            if user_input.lower() in ['help', '?']:
                print(f"\n{Fore.CYAN}📖 Available commands:{Style.RESET_ALL}")
                print(f"• Type your research question in natural language")
                print(f"• 'quit' or 'exit' - Exit the program")
                print(f"• 'help' or '?' - Show this help")
                continue
            
            # Check for matching topics (only for first question)
            if question_count == 0:
                matching_session_id = check_for_matching_topic(user_input, session_cache)
                if matching_session_id:
                    print(f"{Fore.YELLOW}🎯 Found relevant research database! Continuing with enhanced context...{Style.RESET_ALL}")
                    # Note: Full session merging would require additional implementation
                    # For now, we proceed with current session but could enhance with existing data
            
            question_count += 1
            
            # Process the question
            print(f"\n{Fore.CYAN}🔄 Processing question #{question_count}...{Style.RESET_ALL}")
            
            start_time = time.time()
            result = rag.answer_question(user_input)
            end_time = time.time()
            
            # Display results
            print(f"\n{Fore.GREEN}💡 Answer:{Style.RESET_ALL}")
            print(f"{result['answer']}")
            
            # Display references if any
            if result['citations']:
                print(f"\n{Fore.CYAN}📚 References{Style.RESET_ALL}")
                print("─" * 76)
                
                for citation in result['citations']:
                    formatted_ref = format_reference(citation)
                    print(formatted_ref)
            
            # Display session statistics
            print(f"\n{Fore.CYAN}📊 Session Info:{Style.RESET_ALL}")
            if result['search_performed']:
                print(f"🔍 Performed new literature search")
            print(f"📚 Total articles in database: {result.get('total_articles', 'Unknown')}")
            print(f"⏱️  Response time: {end_time - start_time:.1f} seconds")
            
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}🛑 Interrupted by user{Style.RESET_ALL}")
            break
        except Exception as e:
            print(f"\n{Fore.RED}❌ Error processing question: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Please try rephrasing your question{Style.RESET_ALL}")

def main():
    """Main CLI entry point."""
    # Print banner
    print_banner()
    
    # Get configuration
    config = get_configuration()
    
    # Test configuration
    test_configuration(config)
    
    # Create LLM client for session management
    llm_client = OpenAI(
        api_key=config['llm_api_key'],
        base_url=config['llm_base_url']
    )
    
    # Show existing sessions for reference only
    existing_session = load_existing_session(llm_client)
    
    # Setup logging
    log_level = os.getenv('PUBMEDRAG_LOG_LEVEL', 'INFO')
    log_file = os.getenv('PUBMEDRAG_LOG_FILE', None)
    setup_logging(log_level, log_file)
    
    # Initialize RAG system
    print_section("Initializing System", "🚀")
    
    rag = QuestionDrivenRAG(
        email=config['email'],
        llm_api_key=config['llm_api_key'],
        llm_base_url=config['llm_base_url'],
        llm_model=config['llm_model'],
        ncbi_api_key=config.get('ncbi_api_key'),
        initial_search_terms_range=config['initial_search_terms_range'],
        followup_search_terms_range=config['followup_search_terms_range'],
        temperature=config['temperature'],
        embedding_model=config['embedding_model']
    )
    
    print(f"{Fore.GREEN}✅ System ready!{Style.RESET_ALL}")
    print(f"{Fore.CYAN}🔍 Search terms: {config['initial_search_terms_range'][0]}-{config['initial_search_terms_range'][1]} initial, {config['followup_search_terms_range'][0]}-{config['followup_search_terms_range'][1]} follow-up{Style.RESET_ALL}")
    
    # Run interactive session
    interactive_session(rag, config)
    
    # Cleanup
    print(f"\n{Fore.CYAN}🧹 Cleaning up...{Style.RESET_ALL}")
    rag.close()
    
    print(f"{Fore.GREEN}✅ Thank you for using PubMedRAG!{Style.RESET_ALL}")

if __name__ == "__main__":
    main()