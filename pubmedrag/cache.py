# pubmedrag/cache.py
"""
Cache management for PubMedRAG sessions with intelligent topic matching
"""

import os
import json
import pickle
import csv
from typing import List, Dict, Optional, Set, Any, Tuple
from datetime import datetime
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)


class TopicManager:
    """Manage research topics and intelligent session matching."""
    
    def __init__(self, cache_dir: str = "./pubmedrag_cache", llm_client: Optional[OpenAI] = None):
        self.cache_dir = cache_dir
        self.topics_file = os.path.join(cache_dir, "research_topics.csv")
        self.llm_client = llm_client
        
        # Create cache directory
        os.makedirs(cache_dir, exist_ok=True)
        
        # Initialize topics CSV if it doesn't exist
        if not os.path.exists(self.topics_file):
            self._create_topics_csv()
    
    def _create_topics_csv(self):
        """Create the topics CSV file with headers."""
        with open(self.topics_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'session_id', 'topic', 'created_at', 'last_updated', 
                'total_questions', 'total_articles', 'collection_name',
                'first_question', 'keywords'
            ])
    
    def add_topic(self, session_id: str, topic: str, session_data: Dict[str, Any]):
        """Add a new research topic to the CSV."""
        queries = session_data.get('queries', [])
        first_question = queries[0]['question'] if queries else ""
        keywords = self._extract_keywords(topic, first_question)
        
        # Read existing data
        topics = self.load_all_topics()
        
        # Check if session already exists
        existing_index = None
        for i, existing_topic in enumerate(topics):
            if existing_topic['session_id'] == session_id:
                existing_index = i
                break
        
        new_topic_data = {
            'session_id': session_id,
            'topic': topic,
            'created_at': session_data.get('created_at', datetime.now().isoformat()),
            'last_updated': datetime.now().isoformat(),
            'total_questions': len(session_data.get('queries', [])),
            'total_articles': len(session_data.get('indexed_pmids', [])),
            'collection_name': session_data.get('collection_name', ''),
            'first_question': first_question,
            'keywords': keywords
        }
        
        if existing_index is not None:
            # Update existing
            topics[existing_index] = new_topic_data
        else:
            # Add new
            topics.append(new_topic_data)
        
        # Write back to CSV
        self._write_topics_csv(topics)
        logger.info(f"✅ Topic saved: {topic}")
    
    def _extract_keywords(self, topic: str, first_question: str) -> str:
        """Extract keywords from topic and first question."""
        # Simple keyword extraction
        import re
        text = f"{topic} {first_question}".lower()
        # Remove common words and extract potential biomedical terms
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
        # Filter out common words
        common_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 
            'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before', 
            'after', 'above', 'below', 'out', 'off', 'down', 'over', 'under',
            'what', 'how', 'why', 'when', 'where', 'who', 'which', 'that', 'this',
            'are', 'is', 'was', 'were', 'been', 'being', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
            'can', 'cancer', 'study', 'research', 'analysis', 'effect', 'role'
        }
        keywords = [word for word in words if word not in common_words and len(word) > 3]
        return ','.join(keywords[:10])  # Top 10 keywords
    
    def load_all_topics(self) -> List[Dict[str, Any]]:
        """Load all topics from CSV."""
        topics = []
        if os.path.exists(self.topics_file):
            try:
                with open(self.topics_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        topics.append(row)
            except Exception as e:
                logger.warning(f"Error reading topics CSV: {e}")
        return topics
    
    def _write_topics_csv(self, topics: List[Dict[str, Any]]):
        """Write topics to CSV."""
        if not topics:
            return
            
        with open(self.topics_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = topics[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(topics)
    
    def find_matching_topic(self, question: str, similarity_threshold: float = 0.7) -> Optional[Dict[str, Any]]:
        """Find the best matching topic for a question using LLM."""
        if not self.llm_client:
            logger.warning("No LLM client available for topic matching")
            return self._fallback_topic_matching(question)
        
        topics = self.load_all_topics()
        if not topics:
            return None
        
        # Prepare topics for LLM analysis
        topics_summary = []
        for i, topic in enumerate(topics):
            topics_summary.append({
                "index": i,
                "topic": topic['topic'],
                "first_question": topic['first_question'],
                "keywords": topic['keywords'],
                "articles": topic['total_articles'],
                "questions": topic['total_questions']
            })
        
        prompt = f"""
Analyze if the new research question can be answered using an existing research topic's database.

NEW QUESTION: "{question}"

EXISTING TOPICS:
{json.dumps(topics_summary, indent=2)}

Task: Determine if the new question is closely related to any existing topic and can benefit from that topic's literature database.

Criteria for matching:
1. The question addresses the same biological entities, pathways, or medical conditions
2. The existing database would contain relevant literature for the new question
3. The research scope is similar or complementary

Respond in JSON format:
{{
    "has_match": true/false,
    "best_match_index": number or null,
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of why this topic matches or why no match found"
}}
"""
        
        try:
            response = self.llm_client.chat.completions.create(
                model="deepseek-chat",  # Use a default model
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            import re
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if not json_match:
                return self._fallback_topic_matching(question)
            
            result = json.loads(json_match.group())
            
            if result.get("has_match") and result.get("confidence", 0) >= similarity_threshold:
                match_index = result.get("best_match_index")
                if match_index is not None and 0 <= match_index < len(topics):
                    logger.info(f"🎯 Found matching topic: {topics[match_index]['topic']}")
                    logger.info(f"💭 Reasoning: {result.get('reasoning', '')}")
                    return topics[match_index]
            
            logger.info(f"🔍 No suitable topic match found (confidence: {result.get('confidence', 0):.2f})")
            return None
            
        except Exception as e:
            logger.warning(f"Error in topic matching: {e}")
            return self._fallback_topic_matching(question)
    
    def _fallback_topic_matching(self, question: str) -> Optional[Dict[str, Any]]:
        """Fallback topic matching using simple keyword matching."""
        topics = self.load_all_topics()
        if not topics:
            return None
        
        question_words = set(question.lower().split())
        best_match = None
        best_score = 0
        
        for topic in topics:
            # Score based on keyword overlap
            topic_keywords = topic.get('keywords', '').lower().split(',')
            topic_words = set(' '.join([
                topic.get('topic', ''),
                topic.get('first_question', ''),
                ' '.join(topic_keywords)
            ]).lower().split())
            
            overlap = len(question_words & topic_words)
            if overlap > best_score and overlap >= 2:  # Require at least 2 matching words
                best_score = overlap
                best_match = topic
        
        if best_match:
            logger.info(f"🎯 Found matching topic (fallback): {best_match['topic']}")
            return best_match
        
        return None
    
    def get_topic_statistics(self) -> Dict[str, Any]:
        """Get statistics about all topics."""
        topics = self.load_all_topics()
        
        if not topics:
            return {
                "total_topics": 0,
                "total_questions": 0,
                "total_articles": 0,
                "most_recent": None,
                "most_productive": None
            }
        
        total_questions = sum(int(topic.get('total_questions', 0)) for topic in topics)
        total_articles = sum(int(topic.get('total_articles', 0)) for topic in topics)
        
        # Find most recent
        most_recent = max(topics, key=lambda x: x.get('last_updated', ''))
        
        # Find most productive (most articles)
        most_productive = max(topics, key=lambda x: int(x.get('total_articles', 0)))
        
        return {
            "total_topics": len(topics),
            "total_questions": total_questions,
            "total_articles": total_articles,
            "most_recent": most_recent['topic'],
            "most_productive": most_productive['topic']
        }


class SessionCache:
    """Manage session caching for question-driven RAG with topic management."""
    
    def __init__(self, cache_dir: str = "./pubmedrag_cache", llm_client: Optional[OpenAI] = None):
        self.cache_dir = cache_dir
        self.sessions_dir = os.path.join(cache_dir, "sessions")
        self.metadata_file = os.path.join(cache_dir, "sessions_metadata.json")
        self.llm_client = llm_client
        
        # Initialize topic manager
        self.topic_manager = TopicManager(cache_dir, llm_client)
        
        # Create directories
        os.makedirs(self.sessions_dir, exist_ok=True)
        
    def _load_metadata(self) -> Dict[str, Any]:
        """Load sessions metadata."""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading metadata: {e}")
        return {}
    
    def _save_metadata(self, metadata: Dict[str, Any]):
        """Save sessions metadata."""
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    def save_session(self, session_id: str, search_history: Dict[str, Any], 
                    description: str = ""):
        """Save a session to cache and update topic management."""
        # Save session data
        session_file = os.path.join(self.sessions_dir, f"{session_id}.json")
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(search_history, f, ensure_ascii=False, indent=2)
        
        # Update metadata
        metadata = self._load_metadata()
        metadata[session_id] = {
            "session_id": session_id,
            "description": description,
            "created_at": search_history.get("created_at", datetime.now().isoformat()),
            "last_updated": datetime.now().isoformat(),
            "total_questions": len(search_history.get("queries", [])),
            "total_articles": len(search_history.get("indexed_pmids", [])),
            "collection_name": search_history.get("collection_name", ""),
            "topic": search_history.get("topic", ""),
            "questions": [q["question"] for q in search_history.get("queries", [])][:5]  # First 5 questions
        }
        self._save_metadata(metadata)
        
        # Add to topic manager
        topic = search_history.get("topic", "") or description
        if topic:
            self.topic_manager.add_topic(session_id, topic, search_history)
        
        logger.info(f"✅ Session {session_id} saved to cache")
        return True
    
    def find_matching_session(self, question: str) -> Optional[Dict[str, Any]]:
        """Find a session that can answer the question using topic matching."""
        matching_topic = self.topic_manager.find_matching_topic(question)
        if matching_topic:
            session_id = matching_topic['session_id']
            return self.load_session(session_id)
        return None
    
    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a session from cache."""
        session_file = os.path.join(self.sessions_dir, f"{session_id}.json")
        if os.path.exists(session_file):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading session {session_id}: {e}")
        return None
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all cached sessions with topic information."""
        metadata = self._load_metadata()
        sessions = []
        
        for session_id, session_info in metadata.items():
            # Enhance with topic information if available
            topics = self.topic_manager.load_all_topics()
            topic_info = next((t for t in topics if t['session_id'] == session_id), None)
            
            if topic_info:
                session_info['topic'] = topic_info['topic']
                session_info['keywords'] = topic_info['keywords']
            
            sessions.append(session_info)
        
        # Sort by last updated, newest first
        sessions.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
        return sessions
    
    def find_similar_sessions(self, question: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Find sessions with similar questions (fallback method)."""
        metadata = self._load_metadata()
        sessions_with_scores = []
        
        question_lower = question.lower()
        question_words = set(question_lower.split())
        
        for session_id, session_info in metadata.items():
            score = 0
            # Score based on topic similarity
            topic = session_info.get('topic', '').lower()
            topic_words = set(topic.split())
            score += len(question_words & topic_words) * 2  # Topic words weighted higher
            
            # Score based on question similarity
            for prev_question in session_info.get("questions", []):
                prev_words = set(prev_question.lower().split())
                overlap = len(question_words & prev_words)
                score += overlap
            
            if score > 0:
                sessions_with_scores.append({
                    "session": session_info,
                    "score": score
                })
        
        # Sort by score and return top K
        sessions_with_scores.sort(key=lambda x: x["score"], reverse=True)
        return [item["session"] for item in sessions_with_scores[:top_k]]
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a cached session and its topic information."""
        # Delete session file
        session_file = os.path.join(self.sessions_dir, f"{session_id}.json")
        if os.path.exists(session_file):
            os.remove(session_file)
        
        # Update metadata
        metadata = self._load_metadata()
        if session_id in metadata:
            del metadata[session_id]
            self._save_metadata(metadata)
        
        # Remove from topics CSV
        topics = self.topic_manager.load_all_topics()
        topics = [t for t in topics if t['session_id'] != session_id]
        self.topic_manager._write_topics_csv(topics)
        
        logger.info(f"✅ Session {session_id} deleted")
        return True
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        metadata = self._load_metadata()
        topic_stats = self.topic_manager.get_topic_statistics()
        
        total_sessions = len(metadata)
        total_questions = sum(s.get("total_questions", 0) for s in metadata.values())
        total_articles = sum(s.get("total_articles", 0) for s in metadata.values())
        
        # Calculate cache size
        cache_size = 0
        for filename in os.listdir(self.sessions_dir):
            filepath = os.path.join(self.sessions_dir, filename)
            if os.path.isfile(filepath):
                cache_size += os.path.getsize(filepath)
        
        return {
            "total_sessions": total_sessions,
            "total_questions": total_questions,
            "total_articles": total_articles,
            "cache_size_mb": round(cache_size / (1024 * 1024), 2),
            "oldest_session": min(
                (s.get("created_at", "") for s in metadata.values()), 
                default="N/A"
            ),
            "newest_session": max(
                (s.get("last_updated", "") for s in metadata.values()), 
                default="N/A"
            ),
            "topic_statistics": topic_stats
        }


class VectorDBCache:
    """Cache for ChromaDB collections to enable session resumption."""
    
    def __init__(self, cache_dir: str = "./pubmedrag_cache"):
        self.cache_dir = cache_dir
        self.collections_dir = os.path.join(cache_dir, "collections")
        os.makedirs(self.collections_dir, exist_ok=True)
    
    def save_collection_metadata(self, collection_name: str, metadata: Dict[str, Any]):
        """Save collection metadata for future restoration."""
        meta_file = os.path.join(self.collections_dir, f"{collection_name}_meta.json")
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Collection metadata saved: {collection_name}")
    
    def load_collection_metadata(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """Load collection metadata."""
        meta_file = os.path.join(self.collections_dir, f"{collection_name}_meta.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading collection metadata: {e}")
        return None
    
    def collection_exists(self, collection_name: str) -> bool:
        """Check if collection metadata exists."""
        meta_file = os.path.join(self.collections_dir, f"{collection_name}_meta.json")
        return os.path.exists(meta_file)