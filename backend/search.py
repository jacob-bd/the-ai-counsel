"""Web search module with multiple provider support."""

from ddgs import DDGS
from typing import List, Dict, Optional, Set
from enum import Enum
import ipaddress
import logging
import httpx
import os
import time
import asyncio
import yake
import re
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Current year for temporal context
CURRENT_YEAR = datetime.now().year

# YAKE keyword extractor configuration
_keyword_extractor: Optional[yake.KeywordExtractor] = None


def get_keyword_extractor() -> yake.KeywordExtractor:
    """Get or create YAKE keyword extractor (singleton for efficiency)."""
    global _keyword_extractor
    if _keyword_extractor is None:
        _keyword_extractor = yake.KeywordExtractor(
            lan="en",           # Language
            n=3,                # Max n-gram size (up to 3-word phrases)
            dedupLim=0.3,       # Stricter deduplication
            dedupFunc='seqm',   # Sequence matcher for dedup
            top=20,             # Extract more candidates, we'll filter
            features=None       # Use default features
        )
    return _keyword_extractor


# Noise words/phrases to filter out from extracted keywords
NOISE_WORDS = {
    # Action words from prompts
    'act', 'based', 'please', 'help', 'want', 'need', 'know', 'tell',
    'explain', 'describe', 'give', 'provide', 'show', 'make', 'create',
    # Analysis terms
    'question', 'answer', 'think', 'believe', 'consider', 'evaluate',
    'analyze', 'compare', 'discuss', 'strongest', 'arguments', 'theory',
    # Time/context noise
    'current', 'late', 'early', 'recent', 'today', 'now',
    # Common filler
    'like', 'using', 'use', 'way', 'things', 'something',
    # Prepositions/articles (YAKE sometimes includes these)
    'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or'
}

# Phrases that should be filtered entirely
NOISE_PHRASES = {
    'market in late', 'analyst and evaluate', 'evaluate the theory',
    'compare the current', 'based on the', 'act as a', 'tell me about',
    'current market', 'late 2025', 'early 2025', 'in 2025', 'in 2024'
}

# Role-play job titles to filter (common in "act as a..." prompts)
ROLE_PLAY_TITLES = {
    'financial analyst', 'data analyst', 'business analyst', 'market analyst',
    'research analyst', 'investment analyst', 'senior analyst', 'junior analyst',
    'expert', 'specialist', 'consultant', 'advisor', 'professor', 'scientist',
    'economist', 'strategist', 'researcher', 'journalist', 'writer', 'editor'
}

# Current event indicators for intent detection
CURRENT_EVENT_INDICATORS = {
    'latest', 'recent', 'today', 'now', 'current', 'breaking', 'news',
    'this week', 'this month', 'this year', 'yesterday', 'tomorrow',
    'stock', 'price', 'market', 'trading', 'shares', 'crypto', 'bitcoin',
    'election', 'vote', 'poll', 'announcement', 'release', 'launch',
    'update', 'new', 'just', 'happening', 'live', 'weather', 'forecast'
}

# Company/organization patterns that suggest current event queries
COMPANY_PATTERNS = [
    r'\b(apple|google|microsoft|amazon|meta|tesla|nvidia|openai|anthropic)\b',
    r'\b(stock|shares|price|market cap|earnings|revenue)\b',
    r'\b(ceo|cfo|founder|executive|announces?|announced?)\b'
]

# Conversational fluff patterns to remove
CONVERSATIONAL_FLUFF = [
    r'^(can you |could you |please |help me |i want to |i need to |i\'d like to )',
    r'^(tell me (about )?|explain (to me )?(what |how |why )?|describe )',
    r'^(what is |what are |who is |who are |what\'s )',
    r'^(how do i |how can i |how to |what\'s the |what is the )',
    r'^(give me |show me |find |search for |look up )',
    r'(and )?(tell me (about )?|explain )',  # Mid-sentence fluff after role-play removal
    r'( please\??)$',
    r'\?+$'
]


# =============================================================================
# QUERY INTENT DETECTION
# =============================================================================

def detect_query_intent(query: str) -> str:
    """
    Detect the intent of a user query to determine optimal search strategy.
    
    Returns:
        "current_event" - Recent news, prices, live updates
        "factual" - General knowledge, definitions, how-to
        "comparison" - Comparing things, pros/cons
        "research" - In-depth research topics
    """
    query_lower = query.lower()
    
    # Check for current event indicators
    current_event_score = 0
    
    # Direct indicator words
    for indicator in CURRENT_EVENT_INDICATORS:
        if indicator in query_lower:
            current_event_score += 1
    
    # Year references (current or recent years)
    if re.search(rf'\b(20{CURRENT_YEAR % 100}|20{(CURRENT_YEAR - 1) % 100})\b', query_lower):
        current_event_score += 2
    
    # Company/business patterns
    for pattern in COMPANY_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            current_event_score += 1
    
    # Check for comparison intent
    comparison_patterns = [
        r'\bvs\.?\b', r'\bversus\b', r'\bcompare\b', r'\bcomparison\b',
        r'\bdifference between\b', r'\bwhich is better\b', r'\bpros and cons\b',
        r'\badvantages\b', r'\bdisadvantages\b'
    ]
    for pattern in comparison_patterns:
        if re.search(pattern, query_lower):
            return "comparison"
    
    # Check for research/in-depth topics
    research_patterns = [
        r'\bhistory of\b', r'\borigin of\b', r'\bevolution of\b',
        r'\bimpact of\b', r'\beffects of\b', r'\bcauses of\b',
        r'\btheory\b', r'\bresearch\b', r'\bstudy\b', r'\banalysis\b'
    ]
    for pattern in research_patterns:
        if re.search(pattern, query_lower):
            return "research"
    
    # Score-based decision
    if current_event_score >= 2:
        return "current_event"
    
    return "factual"


# =============================================================================
# SMART QUERY OPTIMIZER
# =============================================================================

def optimize_search_query(user_query: str) -> Dict:
    """
    Transform a user query into optimized search queries.
    
    Returns:
        {
            "web_query": "optimized query for web search",
            "news_query": "optimized query for news search",
            "intent": "current_event|factual|comparison|research",
            "original_query": "the original query",
            "entities": ["extracted", "key", "terms"]
        }
    """
    # Detect intent first
    intent = detect_query_intent(user_query)
    
    # Clean the query - remove conversational fluff
    cleaned = user_query.strip()
    for pattern in CONVERSATIONAL_FLUFF:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    
    # If cleaning removed too much, use original
    if len(cleaned) < 5:
        cleaned = user_query.strip()
    
    # Remove role-play patterns
    cleaned = re.sub(
        r'\b(act(ing)?|behave|pretend|imagine you are|you are|be) as (a|an|the)?\s*\w+(\s+\w+)?\b',
        '', cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Remove leading articles that don't add search value
    cleaned = re.sub(r'^(the|a|an)\s+', '', cleaned, flags=re.IGNORECASE)
    
    # Extract key entities (nouns, proper nouns, numbers)
    # Simple approach: keep capitalized words, numbers, and quoted phrases
    entities = []
    
    # Extract quoted phrases
    quoted = re.findall(r'"([^"]+)"', cleaned)
    entities.extend(quoted)
    
    # Extract potential entities (capitalized sequences, numbers with context)
    words = cleaned.split()
    for i, word in enumerate(words):
        # Skip common words
        if word.lower() in NOISE_WORDS:
            continue
        # Keep capitalized words (likely proper nouns)
        if word[0].isupper() and len(word) > 1:
            entities.append(word)
        # Keep numbers with context (e.g., "2026", "$100")
        if re.match(r'^[\$€£]?\d+[\.,]?\d*[%]?$', word):
            entities.append(word)
    
    # Build optimized queries
    web_query = cleaned
    news_query = cleaned
    
    # For current events, add temporal context
    if intent == "current_event":
        # Check if year is already mentioned
        if not re.search(r'\b20\d{2}\b', cleaned):
            news_query = f"{cleaned} {CURRENT_YEAR}"
        else:
            news_query = cleaned
        # For web query, keep as-is since it may need general results too
    
    # For comparisons, structure the query
    if intent == "comparison":
        # Keep as-is, comparison queries usually work well
        pass
    
    # Truncate to reasonable length for search engines
    web_query = web_query[:150].strip()
    news_query = news_query[:150].strip()
    
    logger.info(f"Query optimization: intent={intent}, web_query='{web_query[:50]}...'")
    
    return {
        "web_query": web_query,
        "news_query": news_query,
        "intent": intent,
        "original_query": user_query,
        "entities": list(set(entities))[:10]  # Dedupe and limit
    }


# =============================================================================
# RELEVANCE SCORING
# =============================================================================

def _tokenize(text: str) -> Set[str]:
    """Simple tokenization for relevance scoring."""
    # Lowercase and extract words
    words = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
    # Filter out very short words and common stop words
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                  'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                  'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                  'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
                  'as', 'into', 'through', 'during', 'before', 'after', 'above',
                  'below', 'between', 'under', 'again', 'further', 'then', 'once',
                  'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each',
                  'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
                  'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
                  'can', 'just', 'don', 'now', 'and', 'but', 'or', 'because',
                  'this', 'that', 'these', 'those', 'it', 'its'}
    return {w for w in words if len(w) > 2 and w not in stop_words}


def score_result_relevance(result: Dict, query_terms: Set[str], intent: str = "factual") -> float:
    """
    Score a search result's relevance to the query.
    
    Args:
        result: Search result dict with 'title', 'summary', 'url' keys
        query_terms: Set of query terms (tokenized)
        intent: Query intent for context-specific scoring
    
    Returns:
        Relevance score from 0.0 to 1.0
    """
    if not query_terms:
        return 0.5  # Neutral score if no terms
    
    score = 0.0
    
    # Title match (highest weight - 0.4)
    title = result.get('title', '')
    title_terms = _tokenize(title)
    title_overlap = len(query_terms & title_terms)
    title_score = min(title_overlap / max(len(query_terms), 1), 1.0)
    score += title_score * 0.4
    
    # Summary/body match (medium weight - 0.35)
    summary = result.get('summary', '') or result.get('body', '')
    summary_terms = _tokenize(summary)
    summary_overlap = len(query_terms & summary_terms)
    summary_score = min(summary_overlap / max(len(query_terms), 1), 1.0)
    score += summary_score * 0.35
    
    # URL quality signals (low weight - 0.15)
    url = result.get('url', '').lower()
    url_score = 0.5  # Base score
    
    # Boost authoritative domains
    authoritative_domains = [
        'wikipedia.org', 'britannica.com', 'reuters.com', 'apnews.com',
        'bbc.com', 'bbc.co.uk', 'nytimes.com', 'wsj.com', 'bloomberg.com',
        'techcrunch.com', 'theverge.com', 'arstechnica.com', 'wired.com',
        'nature.com', 'science.org', 'gov', 'edu'
    ]
    for domain in authoritative_domains:
        if domain in url:
            url_score = 0.9
            break
    
    # Penalize low-quality indicators
    low_quality_indicators = ['pinterest', 'facebook.com', 'twitter.com', 
                              'instagram.com', 'tiktok.com', 'reddit.com/user/']
    for indicator in low_quality_indicators:
        if indicator in url:
            url_score = 0.2
            break
    
    score += url_score * 0.15
    
    # Freshness bonus for current events (0.1 weight)
    if intent == "current_event":
        # Check for recent date indicators in summary
        freshness_score = 0.3  # Base
        current_year_str = str(CURRENT_YEAR)
        if current_year_str in summary or current_year_str in title:
            freshness_score = 0.8
        # Check for time indicators
        time_indicators = ['today', 'yesterday', 'this week', 'hours ago', 'minutes ago']
        for indicator in time_indicators:
            if indicator in summary.lower():
                freshness_score = 1.0
                break
        score += freshness_score * 0.1
    else:
        # For non-current-event queries, give neutral freshness score
        score += 0.5 * 0.1
    
    return min(score, 1.0)


def rerank_results(results: List[Dict], query: str, intent: str = "factual") -> List[Dict]:
    """
    Rerank search results by relevance to the query.
    
    Args:
        results: List of search result dicts
        query: Original user query
        intent: Query intent
    
    Returns:
        Reranked list of results (highest relevance first)
    """
    query_terms = _tokenize(query)
    
    # Score each result
    scored_results = []
    for result in results:
        relevance = score_result_relevance(result, query_terms, intent)
        result['relevance_score'] = relevance
        scored_results.append(result)
    
    # Sort by relevance score (descending)
    scored_results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
    
    logger.info(f"Reranked {len(results)} results. Top score: {scored_results[0].get('relevance_score', 0):.2f}" if scored_results else "No results to rerank")
    
    return scored_results


def _preprocess_query(query: str) -> str:
    """
    Remove noise phrases and role-play titles from query BEFORE keyword extraction.
    This prevents YAKE from extracting words from these phrases.
    """
    import re
    cleaned = query

    # Remove role-play patterns like "act as a financial analyst"
    # This catches variations like "act as an expert", "acting as a consultant", etc.
    cleaned = re.sub(r'\b(act(ing)?|behave|pretend|imagine you are|you are|be) as (a|an|the)?\s*\w+(\s+\w+)?\b', '', cleaned, flags=re.IGNORECASE)

    # Remove specific role-play titles
    for title in ROLE_PLAY_TITLES:
        cleaned = re.sub(rf'\b{re.escape(title)}\b', '', cleaned, flags=re.IGNORECASE)

    # Remove noise phrases
    for phrase in NOISE_PHRASES:
        cleaned = re.sub(rf'\b{re.escape(phrase)}\b', '', cleaned, flags=re.IGNORECASE)

    # Clean up extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned


def extract_search_keywords(query: str, max_keywords: int = 6) -> str:
    """
    Extract keywords from a user query using YAKE.
    Returns a space-separated string of keywords suitable for search engines.

    Args:
        query: The user's natural language query
        max_keywords: Maximum number of keywords to extract

    Returns:
        Optimized search query string
    """
    if not query or len(query.strip()) < 10:
        # Query too short, use as-is
        return query.strip()

    try:
        # Pre-process: Remove noise phrases and role-play titles BEFORE YAKE extraction
        cleaned_query = _preprocess_query(query)

        extractor = get_keyword_extractor()
        # YAKE returns list of (keyword, score) tuples, lower score = more important
        keywords = extractor.extract_keywords(cleaned_query)

        if not keywords:
            return query.strip()

        # Filter and clean keywords
        clean_keywords = []
        for kw, score in keywords:
            kw_lower = kw.lower()

            # Skip known noise phrases
            if kw_lower in NOISE_PHRASES:
                continue

            # Skip role-play job titles
            if kw_lower in ROLE_PLAY_TITLES:
                continue

            # Skip single-word noise
            words = kw_lower.split()
            if len(words) == 1 and words[0] in NOISE_WORDS:
                continue

            # Skip phrases where most words are noise
            non_noise_words = [w for w in words if w not in NOISE_WORDS]
            if len(non_noise_words) == 0:
                continue
            if len(words) > 1 and len(non_noise_words) < len(words) * 0.4:
                continue

            clean_keywords.append(kw)
            if len(clean_keywords) >= max_keywords:
                break

        # Remove keywords that are substrings of other keywords
        final_keywords = []
        for kw in clean_keywords:
            kw_lower = kw.lower()
            # Check if this keyword is a substring of any other keyword
            is_substring = False
            for other in clean_keywords:
                if kw != other and kw_lower in other.lower():
                    is_substring = True
                    break
            if not is_substring:
                final_keywords.append(kw)

        # Join into search query
        search_query = " ".join(final_keywords)

        logger.info(f"YAKE extracted keywords: '{search_query}' from query: '{query[:50]}...'")

        return search_query if search_query else query.strip()

    except Exception as e:
        logger.warning(f"YAKE keyword extraction failed: {e}, using original query")
        return query.strip()

# Rate limit handling
MAX_RETRIES = 2
RETRY_DELAY = 2  # seconds

# Total timeout budget for all search operations (including content fetching)
SEARCH_TIMEOUT_BUDGET = 60  # seconds total

# Persistent HTTP clients for connection pooling
_async_client: Optional[httpx.AsyncClient] = None
_sync_client: Optional[httpx.Client] = None


def get_async_client() -> httpx.AsyncClient:
    """Get or create persistent async HTTP client for connection pooling."""
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(timeout=30.0)
    return _async_client


def get_sync_client() -> httpx.Client:
    """Get or create persistent sync HTTP client for connection pooling."""
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(timeout=30.0)
    return _sync_client


class SearchProvider(str, Enum):
    DUCKDUCKGO = "duckduckgo"
    TAVILY = "tavily"
    BRAVE = "brave"
    SERPER = "serper"
    TINYFISH = "tinyfish"


async def perform_web_search(
    query: str,
    max_results: int = 8,
    provider: SearchProvider = SearchProvider.DUCKDUCKGO,
    full_content_results: int = 3,
    keyword_extraction: str = "direct",
    hybrid_mode: bool = True
) -> Dict[str, str]:
    """
    Perform a web search using the specified provider.

    Args:
        query: The search query
        max_results: Maximum number of results to return (default 8, up from 5)
        provider: Which search provider to use
        full_content_results: Number of top results to fetch full content for (0 to disable)
        keyword_extraction: "yake" for keyword extraction, "direct" for raw query
        hybrid_mode: For DuckDuckGo, whether to combine web+news search (default True)

    Returns:
        Dict with 'results' (formatted string), 'extracted_query' (query used), 'intent' (detected intent)
    """
    # For DuckDuckGo with new optimization, we handle query processing internally
    # For other providers, use the legacy keyword extraction if enabled
    if provider != SearchProvider.DUCKDUCKGO:
        if keyword_extraction == "yake":
            extracted_query = extract_search_keywords(query)
        else:
            extracted_query = query.strip()
    else:
        # DuckDuckGo uses internal query optimization
        extracted_query = query.strip()

    try:
        if provider == SearchProvider.TAVILY:
            results = await _search_tavily(extracted_query, max_results)
            return {"results": results, "extracted_query": extracted_query, "intent": "unknown"}
        elif provider == SearchProvider.BRAVE:
            results = await _search_brave(extracted_query, max_results, full_content_results)
            return {"results": results, "extracted_query": extracted_query, "intent": "unknown"}
        elif provider == SearchProvider.SERPER:
            results = await _search_serper(extracted_query, max_results, full_content_results)
            return {"results": results, "extracted_query": extracted_query, "intent": "unknown"}
        elif provider == SearchProvider.TINYFISH:
            results = await _search_tinyfish(extracted_query, max_results, full_content_results)
            return {"results": results, "extracted_query": extracted_query, "intent": "unknown"}
        else:
            # DuckDuckGo - now with hybrid search, optimization, and reranking
            query_info = optimize_search_query(query)
            results = await _search_duckduckgo(
                query, 
                max_results, 
                full_content_results,
                hybrid_mode=hybrid_mode
            )
            return {
                "results": results, 
                "extracted_query": query_info["web_query"],
                "intent": query_info["intent"]
            }

    except Exception as e:
        logger.error(f"Error performing web search with {provider}: {str(e)}")
        return {
            "results": "[System Note: Web search was attempted but failed. Please answer based on your internal knowledge.]",
            "extracted_query": extracted_query,
            "intent": "unknown"
        }


async def _search_duckduckgo(
    query: str, 
    max_results: int = 8, 
    full_content_results: int = 3,
    hybrid_mode: bool = True
) -> str:
    """
    Search using DuckDuckGo with hybrid web+news strategy and intelligent reranking.
    
    Features:
    - Query optimization (removes fluff, adds temporal context)
    - Hybrid search (combines web and news results)
    - Relevance-based reranking
    - Parallel content fetching via Jina Reader
    
    Args:
        query: User's search query
        max_results: Maximum final results to return
        full_content_results: Number of top results to fetch full content for
        hybrid_mode: Whether to combine web and news search
    """
    start_time = time.time()
    
    # Step 1: Optimize the query
    query_info = optimize_search_query(query)
    intent = query_info["intent"]
    web_query = query_info["web_query"]
    news_query = query_info["news_query"]
    
    print(f"🔍 Search intent: {intent}")
    print(f"🔍 Web query: '{web_query[:60]}...'")
    if hybrid_mode:
        print(f"🔍 News query: '{news_query[:60]}...'")

    # Step 2: Run searches (hybrid or single based on intent and settings)
    def _do_ddgs_search():
        """Sync helper for DDGS library which doesn't support async."""
        web_results = []
        news_results = []
        
        # Determine search strategy based on intent
        do_web_search = True
        do_news_search = hybrid_mode and intent in ("current_event", "factual")
        
        # Adjust result counts for hybrid mode
        if hybrid_mode and do_news_search:
            web_count = max(max_results - 2, 4)  # More web results
            news_count = max(4, max_results // 2)  # Fewer news results
        else:
            web_count = max_results + 2  # Fetch extra to allow filtering
            news_count = 0
        
        for attempt in range(MAX_RETRIES + 1):
            try:
                with DDGS() as ddgs:
                    # Web search
                    if do_web_search:
                        try:
                            raw_web = list(ddgs.text(web_query, max_results=web_count))
                            for result in raw_web:
                                web_results.append({
                                    'title': result.get('title', 'No Title'),
                                    'url': result.get('url', result.get('href', '#')),
                                    'summary': result.get('body', result.get('excerpt', '')),
                                    'source': result.get('source', ''),
                                    'type': 'web',
                                    'content': None
                                })
                        except Exception as e:
                            logger.warning(f"Web search failed: {e}")
                    
                    # News search (for hybrid mode)
                    if do_news_search and news_count > 0:
                        try:
                            raw_news = list(ddgs.news(news_query, max_results=news_count))
                            for result in raw_news:
                                news_results.append({
                                    'title': result.get('title', 'No Title'),
                                    'url': result.get('url', result.get('link', '#')),
                                    'summary': result.get('body', result.get('excerpt', '')),
                                    'source': result.get('source', ''),
                                    'type': 'news',
                                    'date': result.get('date', ''),
                                    'content': None
                                })
                        except Exception as e:
                            logger.warning(f"News search failed: {e}")
                    
                    break  # Success, exit retry loop
                    
            except Exception as e:
                if "Ratelimit" in str(e) and attempt < MAX_RETRIES:
                    logger.warning(f"DuckDuckGo rate limit hit, retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    raise
        
        return web_results, news_results

    # Execute sync DDGS search in thread pool
    web_results, news_results = await asyncio.to_thread(_do_ddgs_search)
    
    print(f"📊 Got {len(web_results)} web results, {len(news_results)} news results")
    
    # Step 3: Merge and deduplicate results
    all_results = []
    seen_urls = set()
    
    # Add web results first
    for r in web_results:
        url_normalized = r['url'].lower().rstrip('/')
        if url_normalized not in seen_urls:
            seen_urls.add(url_normalized)
            all_results.append(r)
    
    # Add news results (avoid duplicates)
    for r in news_results:
        url_normalized = r['url'].lower().rstrip('/')
        if url_normalized not in seen_urls:
            seen_urls.add(url_normalized)
            all_results.append(r)
    
    if not all_results:
        return "No web search results found."
    
    # Step 4: Rerank by relevance to original query
    all_results = rerank_results(all_results, query, intent)
    
    # Step 5: Take top results
    final_results = all_results[:max_results]
    
    # Assign final indices
    for i, r in enumerate(final_results, 1):
        r['index'] = i
    
    print(f"🎯 Selected top {len(final_results)} results after reranking")
    
    # Step 6: Fetch full content for top N results IN PARALLEL
    urls_to_fetch = []
    for i, r in enumerate(final_results):
        if full_content_results > 0 and i < full_content_results:
            url = r.get('url', '')
            if url and url != '#':
                urls_to_fetch.append((i, url))
    
    if urls_to_fetch:
        elapsed = time.time() - start_time
        remaining = SEARCH_TIMEOUT_BUDGET - elapsed

        if remaining > 5:  # Need at least 5s to fetch content
            fetch_timeout = min(remaining, 25.0)

            async def fetch_with_index(idx: int, url: str):
                """Wrapper to return index along with content for result mapping."""
                content = await _fetch_with_jina(url, timeout=fetch_timeout)
                return (idx, content)

            tasks = [fetch_with_index(idx, url) for idx, url in urls_to_fetch]

            print(f"⚡ Starting PARALLEL fetch of {len(tasks)} URLs via Jina Reader...")
            fetch_start = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            fetch_elapsed = time.time() - fetch_start
            print(f"⚡ Parallel fetch completed in {fetch_elapsed:.2f}s")

            successful = 0
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Parallel Jina fetch failed: {result}")
                    continue

                idx, content = result
                if content:
                    successful += 1
                    if len(content) < 500:
                        original_summary = final_results[idx]['summary']
                        content += f"\n\n[System Note: Full content fetch yielded limited text.]\nOriginal Summary: {original_summary}"
                    final_results[idx]['content'] = content
            print(f"⚡ Successfully fetched content from {successful}/{len(tasks)} URLs")
        else:
            logger.warning("Search timeout budget exhausted, skipping content fetches")

    # Step 7: Format results
    formatted = []
    for r in final_results:
        text = f"Result {r['index']}:\nTitle: {r['title']}\nURL: {r['url']}"
        if r.get('source'):
            text += f"\nSource: {r['source']}"
        if r.get('type') == 'news' and r.get('date'):
            text += f"\nDate: {r['date']}"
        if r.get('relevance_score'):
            text += f"\n[Relevance: {r['relevance_score']:.2f}]"
        if r.get('content'):
            content = r['content'][:2000]
            if len(r['content']) > 2000:
                content += "..."
            text += f"\nContent:\n{content}"
        else:
            text += f"\nSummary: {r['summary']}"
        formatted.append(text)

    return "\n\n".join(formatted)


def _is_safe_fetch_url(url: str) -> bool:
    """Reject URLs that target internal networks before sending them to Jina Reader.

    Search results are attacker-influenced, so a poisoned result containing
    e.g. http://169.254.169.254/ or http://10.0.0.5/ could turn Jina into an
    SSRF probe against the host's metadata service or LAN. We require an http/
    https scheme and a hostname that is not an obvious internal-IP literal.
    Hostnames that resolve via DNS to private addresses are not blocked here
    (DNS rebinding is out of scope); the goal is to stop direct IP-literal
    attacks without imposing a network round-trip on every URL.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # Not an IP literal — let the request proceed.
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)


def _fetch_with_jina_sync(url: str, timeout: float = 25.0) -> Optional[str]:
    """
    Fetch article content using Jina Reader API (sync version for DuckDuckGo).
    Returns clean markdown content. Uses connection pooling.
    """
    if not _is_safe_fetch_url(url):
        logger.warning("Refusing to fetch unsafe URL via Jina: %s", url)
        return None
    try:
        jina_url = f"https://r.jina.ai/{url}"
        client = get_sync_client()
        response = client.get(jina_url, headers={
            "Accept": "text/plain",
        }, timeout=timeout)
        if response.status_code == 200:
            return response.text
        else:
            logger.warning(f"Jina Reader returned {response.status_code} for {url}")
            return None
    except httpx.TimeoutException:
        logger.warning(f"Timeout while fetching content via Jina for {url}")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch content via Jina for {url}: {e}")
        return None


async def _fetch_with_jina(url: str, timeout: float = 25.0) -> Optional[str]:
    """
    Fetch article content using Jina Reader API (async).
    Returns clean markdown content. Uses connection pooling.
    """
    if not _is_safe_fetch_url(url):
        logger.warning("Refusing to fetch unsafe URL via Jina: %s", url)
        return None
    try:
        jina_url = f"https://r.jina.ai/{url}"
        client = get_async_client()
        response = await client.get(jina_url, headers={
            "Accept": "text/plain",
        }, timeout=timeout)
        if response.status_code == 200:
            return response.text
        else:
            logger.warning(f"Jina Reader returned {response.status_code} for {url}")
            return None
    except httpx.TimeoutException:
        logger.warning(f"Timeout while fetching content via Jina for {url}")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch content via Jina for {url}: {e}")
        return None


async def _search_tavily(query: str, max_results: int = 5) -> str:
    """
    Search using Tavily API (designed for LLM/RAG use cases, async).
    Requires TAVILY_API_KEY environment variable. Uses connection pooling.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        logger.error("TAVILY_API_KEY not set")
        return "[System Note: Tavily API key not configured. Please add TAVILY_API_KEY to your environment.]"

    try:
        client = get_async_client()
        response = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
                "search_depth": "advanced",
            },
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for i, result in enumerate(data.get("results", []), 1):
            title = result.get("title", "No Title")
            url = result.get("url", "#")
            content = result.get("content", "No content available.")

            text = f"Result {i}:\nTitle: {title}\nURL: {url}\nContent:\n{content}"
            results.append(text)

        if not results:
            return "No web search results found."

        return "\n\n".join(results)

    except httpx.HTTPStatusError as e:
        logger.error(f"Tavily API error: {e.response.status_code} - {e.response.text}")
        return "[System Note: Tavily search failed. Please check your API key.]"
    except Exception as e:
        logger.error(f"Tavily search error: {e}")
        return "[System Note: Tavily search failed. Please try again.]"


async def _search_brave(query: str, max_results: int = 5, full_content_results: int = 3) -> str:
    """
    Search using Brave Search API (async).
    Optionally fetches full content via Jina Reader for top N results.
    Requires BRAVE_API_KEY environment variable. Uses connection pooling.
    """
    start_time = time.time()
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        logger.error("BRAVE_API_KEY not set")
        return "[System Note: Brave API key not configured. Please add your Brave API key in settings.]"

    try:
        client = get_async_client()
        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={
                "q": query,
                "count": max_results,
            },
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
        )
        response.raise_for_status()
        data = response.json()

        search_results_data = []
        urls_to_fetch = []
        web_results = data.get("web", {}).get("results", [])

        for i, result in enumerate(web_results[:max_results], 1):
            title = result.get("title", "No Title")
            url = result.get("url", "#")
            description = result.get("description", "No description available.")

            # Some results have extra_snippets with more content
            extra = result.get("extra_snippets", [])
            if extra:
                description += "\n" + "\n".join(extra[:2])

            search_results_data.append({
                'index': i,
                'title': title,
                'url': url,
                'summary': description,
                'content': None
            })

            # Queue top N results for full content fetch
            if full_content_results > 0 and i <= full_content_results and url and url != '#':
                urls_to_fetch.append((i - 1, url))

        # Fetch full content via Jina Reader for top results
        for idx, url in urls_to_fetch:
            # Check remaining time budget
            elapsed = time.time() - start_time
            remaining = SEARCH_TIMEOUT_BUDGET - elapsed

            if remaining <= 5:  # Need at least 5s to fetch content
                logger.warning("Search timeout budget exhausted, skipping remaining content fetches")
                break

            # Use remaining time as timeout for this fetch
            content = await _fetch_with_jina(url, timeout=min(remaining, 25.0))
            if content:
                # If content is very short, append summary
                if len(content) < 500:
                    original_summary = search_results_data[idx]['summary']
                    content += f"\n\n[System Note: Full content fetch yielded limited text. Appending original summary.]\nOriginal Summary: {original_summary}"
                search_results_data[idx]['content'] = content

        if not search_results_data:
            return "No web search results found."

        # Format results
        formatted = []
        for r in search_results_data:
            text = f"Result {r['index']}:\nTitle: {r['title']}\nURL: {r['url']}"
            if r['content']:
                # Truncate content to ~2000 chars
                content = r['content'][:2000]
                if len(r['content']) > 2000:
                    content += "..."
                text += f"\nContent:\n{content}"
            else:
                text += f"\nSummary: {r['summary']}"
            formatted.append(text)

        return "\n\n".join(formatted)

    except httpx.HTTPStatusError as e:
        logger.error(f"Brave API error: {e.response.status_code} - {e.response.text}")
        return "[System Note: Brave search failed. Please check your API key.]"
    except Exception as e:
        logger.error(f"Brave search error: {e}")
        return "[System Note: Brave search failed. Please try again.]"


async def _search_serper(query: str, max_results: int = 10, full_content_results: int = 3) -> str:
    """
    Search using Serper.dev API (Google Search results).
    Optionally fetches full content via Jina Reader for top N results.
    Requires SERPER_API_KEY environment variable. Uses connection pooling.
    """
    start_time = time.time()
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        logger.error("SERPER_API_KEY not set")
        return "[System Note: Serper API key not configured. Please add your Serper API key in settings.]"

    try:
        client = get_async_client()
        response = await client.post(
            "https://google.serper.dev/search",
            json={
                "q": query,
                "num": min(max_results, 10),  # Serper max is 10 per request
            },
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()

        search_results_data = []
        urls_to_fetch = []
        
        # Process organic results
        organic_results = data.get("organic", [])
        
        for i, result in enumerate(organic_results[:max_results], 1):
            title = result.get("title", "No Title")
            url = result.get("link", "#")
            snippet = result.get("snippet", "No description available.")
            position = result.get("position", i)

            search_results_data.append({
                'index': i,
                'title': title,
                'url': url,
                'summary': snippet,
                'position': position,
                'content': None
            })

            # Queue top N results for full content fetch
            if full_content_results > 0 and i <= full_content_results and url and url != '#':
                urls_to_fetch.append((i - 1, url))

        # Fetch full content via Jina Reader for top results IN PARALLEL
        if urls_to_fetch:
            elapsed = time.time() - start_time
            remaining = SEARCH_TIMEOUT_BUDGET - elapsed

            if remaining > 5:
                fetch_timeout = min(remaining, 25.0)

                async def fetch_with_index(idx: int, url: str):
                    content = await _fetch_with_jina(url, timeout=fetch_timeout)
                    return (idx, content)

                tasks = [fetch_with_index(idx, url) for idx, url in urls_to_fetch]

                print(f"⚡ Serper: Starting PARALLEL fetch of {len(tasks)} URLs via Jina Reader...")
                fetch_start = time.time()
                results = await asyncio.gather(*tasks, return_exceptions=True)
                fetch_elapsed = time.time() - fetch_start
                print(f"⚡ Serper: Parallel fetch completed in {fetch_elapsed:.2f}s")

                successful = 0
                for result in results:
                    if isinstance(result, Exception):
                        logger.warning(f"Parallel Jina fetch failed: {result}")
                        continue

                    idx, content = result
                    if content:
                        successful += 1
                        if len(content) < 500:
                            original_summary = search_results_data[idx]['summary']
                            content += f"\n\n[System Note: Full content fetch yielded limited text.]\nOriginal Summary: {original_summary}"
                        search_results_data[idx]['content'] = content
                print(f"⚡ Serper: Successfully fetched content from {successful}/{len(tasks)} URLs")
            else:
                logger.warning("Search timeout budget exhausted, skipping content fetches")

        if not search_results_data:
            return "No web search results found."

        # Format results
        formatted = []
        for r in search_results_data:
            text = f"Result {r['index']}:\nTitle: {r['title']}\nURL: {r['url']}"
            if r.get('content'):
                content = r['content'][:2000]
                if len(r['content']) > 2000:
                    content += "..."
                text += f"\nContent:\n{content}"
            else:
                text += f"\nSummary: {r['summary']}"
            formatted.append(text)

        return "\n\n".join(formatted)

    except httpx.HTTPStatusError as e:
        logger.error(f"Serper API error: {e.response.status_code} - {e.response.text}")
        return "[System Note: Serper search failed. Please check your API key.]"
    except Exception as e:
        logger.error(f"Serper search error: {e}")
        return "[System Note: Serper search failed. Please try again.]"


async def _search_tinyfish(query: str, max_results: int = 8, full_content_results: int = 3) -> str:
    """
    Search using TinyFish Search API (async).
    Optionally fetches full content via TinyFish Fetch API (batch) for top N results,
    falling back to Jina Reader for any URLs that fail in the batch response.
    Requires TINYFISH_API_KEY environment variable. Uses connection pooling.
    """
    start_time = time.time()
    api_key = os.environ.get("TINYFISH_API_KEY")
    if not api_key:
        logger.error("TINYFISH_API_KEY not set")
        return "[System Note: TinyFish API key not configured. Please add your TinyFish API key in settings.]"

    try:
        client = get_async_client()
        response = await client.get(
            "https://api.search.tinyfish.ai/",
            params={
                "query": query,
                "location": "us",
                "language": "en",
            },
            headers={
                "X-API-Key": api_key,
            },
        )
        response.raise_for_status()
        data = response.json()

        search_results_data = []
        urls_to_fetch = []

        # TinyFish always returns 10 results — slice to max_results
        raw_results = data.get("results", [])[:max_results]

        for i, result in enumerate(raw_results, 1):
            title = result.get("title", "No Title")
            url = result.get("url", "#")
            snippet = result.get("snippet", "No description available.")

            search_results_data.append({
                'index': i,
                'title': title,
                'url': url,
                'summary': snippet,
                'content': None
            })

            # Queue top N results for full content fetch
            if full_content_results > 0 and i <= full_content_results and url and url != '#':
                urls_to_fetch.append((i - 1, url))

        # Fetch full content via TinyFish Fetch API (batch) for top results
        if urls_to_fetch:
            elapsed = time.time() - start_time
            remaining = SEARCH_TIMEOUT_BUDGET - elapsed

            if remaining > 5:  # Need at least 5s to fetch content
                batch_urls = [url for _, url in urls_to_fetch]
                idx_map = {url: idx for idx, url in urls_to_fetch}

                try:
                    fetch_response = await client.post(
                        "https://api.fetch.tinyfish.ai/",
                        json={
                            "urls": batch_urls,
                            "format": "markdown",
                        },
                        headers={
                            "X-API-Key": api_key,
                        },
                        timeout=min(remaining, 25.0),
                    )
                    fetch_response.raise_for_status()
                    fetch_data = fetch_response.json()

                    # Process successful fetches
                    for item in fetch_data.get("results", []):
                        url = item.get("url", "")
                        content = item.get("text", "")
                        idx = idx_map.get(url)
                        if idx is not None and content:
                            if len(content) < 500:
                                original_summary = search_results_data[idx]['summary']
                                content += f"\n\n[System Note: Full content fetch yielded limited text. Appending original summary.]\nOriginal Summary: {original_summary}"
                            search_results_data[idx]['content'] = content

                    # Fall back to Jina Reader for URLs that appeared in errors[]
                    failed_urls = {err.get("url", "") for err in fetch_data.get("errors", [])}
                    for url in failed_urls:
                        idx = idx_map.get(url)
                        if idx is None:
                            continue
                        elapsed = time.time() - start_time
                        remaining = SEARCH_TIMEOUT_BUDGET - elapsed
                        if remaining <= 5:
                            logger.warning("Search timeout budget exhausted, skipping Jina fallback fetches")
                            break
                        logger.warning(f"TinyFish Fetch failed for {url}, falling back to Jina Reader")
                        content = await _fetch_with_jina(url, timeout=min(remaining, 25.0))
                        if content:
                            if len(content) < 500:
                                original_summary = search_results_data[idx]['summary']
                                content += f"\n\n[System Note: Full content fetch yielded limited text. Appending original summary.]\nOriginal Summary: {original_summary}"
                            search_results_data[idx]['content'] = content

                except httpx.HTTPStatusError as e:
                    logger.warning(f"TinyFish Fetch API error: {e.response.status_code} - {e.response.text}, skipping full content")
                except Exception as e:
                    logger.warning(f"TinyFish Fetch API error: {e}, skipping full content")
            else:
                logger.warning("Search timeout budget exhausted, skipping content fetches")

        if not search_results_data:
            return "No web search results found."

        # Format results
        formatted = []
        for r in search_results_data:
            text = f"Result {r['index']}:\nTitle: {r['title']}\nURL: {r['url']}"
            if r['content']:
                # Truncate content to ~2000 chars
                content = r['content'][:2000]
                if len(r['content']) > 2000:
                    content += "..."
                text += f"\nContent:\n{content}"
            else:
                text += f"\nSummary: {r['summary']}"
            formatted.append(text)

        return "\n\n".join(formatted)

    except httpx.HTTPStatusError as e:
        logger.error(f"TinyFish API error: {e.response.status_code} - {e.response.text}")
        return "[System Note: TinyFish search failed. Please check your API key.]"
    except Exception as e:
        logger.error(f"TinyFish search error: {e}")
        return "[System Note: TinyFish search failed. Please try again.]"
