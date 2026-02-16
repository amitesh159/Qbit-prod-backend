"""
Web Search Service - LangSearch API Integration

Provides semantic search with reranking for:
- Market research
- Latest information
- Competition analysis
- Technical documentation lookup
"""
import httpx
import structlog
from typing import List, Dict, Any
from config.settings import settings

logger = structlog.get_logger(__name__)

# Safe debug logger import
try:
    from utils.debug_logger import dlog
except ImportError:
    def dlog(*args, **kwargs): pass


async def perform_web_search(
    query: str,
    max_results: int = 5
) -> List[Dict[str, Any]]:
    """
    Perform web search using LangSearch API with semantic reranking.
    
    Args:
        query: Search query
        max_results: Maximum number of results to return
        
    Returns:
        List of search results with title, snippet, url
    """
    try:
        # For now, use a simple DuckDuckGo search as fallback
        # TODO: Integrate actual LangSearch API when available
        results = await _duckduckgo_search(query, max_results)
        
        dlog("WebSearch", f"Found {len(results)} results for: {query}")
        
        return results
        
    except Exception as e:
        logger.exception("web_search_failed", error=str(e), query=query)
        return []


async def _duckduckgo_search(query: str, max_results: int) -> List[Dict[str, Any]]:
    """
    Fallback search using DuckDuckGo API.
    
    TODO: Replace with LangSearch API integration for:
    - Semantic understanding
    - Result reranking
    - Domain-specific search
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # DuckDuckGo Instant Answer API
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1
                }
            )
            
            if response.status_code != 200:
                logger.warning("duckduckgo_api_error", status=response.status_code)
                return []
            
            data = response.json()
            
            # Extract results
            results = []
            
            # Abstract (instant answer)
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", "Search Result"),
                    "snippet": data.get("Abstract", ""),
                    "url": data.get("AbstractURL", "")
                })
            
            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("Text", "")[:100],
                        "snippet": topic.get("Text", ""),
                        "url": topic.get("FirstURL", "")
                    })
            
            return results[:max_results]
            
    except Exception as e:
        logger.exception("duckduckgo_search_failed", error=str(e))
        return []


async def search_with_langsearch(
    query: str,
    max_results: int = 5,
    rerank: bool = True
) -> List[Dict[str, Any]]:
    """
    Professional web search with LangSearch API.
    
    Features:
    - Semantic understanding of queries
    - Result reranking based on relevance
    - Domain-specific filtering
    - Multi-source aggregation
    
    TODO: Implement when LangSearch API credentials are available
    
    Args:
        query: Search query
        max_results: Maximum results
        rerank: Enable semantic reranking
        
    Returns:
        List of search results
    """
    # Placeholder for LangSearch API integration
    # Will be implemented when API key is available
    
    langsearch_api_key = settings.langsearch_api_key if hasattr(settings, 'langsearch_api_key') else None
    
    if not langsearch_api_key:
        logger.warning("langsearch_api_key_not_configured_using_fallback")
        return await _duckduckgo_search(query, max_results)
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Example LangSearch API call (adjust based on actual API docs)
            response = await client.post(
                "https://api.langsearch.io/v1/search",  # Placeholder URL
                headers={
                    "Authorization": f"Bearer {langsearch_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "query": query,
                    "max_results": max_results,
                    "rerank": rerank,
                    "filters": {
                        "content_type": ["article", "documentation", "tutorial"],
                        "date_range": "past_year"
                    }
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("results", [])
            else:
                logger.warning("langsearch_api_error", status=response.status_code)
                return await _duckduckgo_search(query, max_results)
                
    except Exception as e:
        logger.exception("langsearch_api_failed", error=str(e))
        return await _duckduckgo_search(query, max_results)
