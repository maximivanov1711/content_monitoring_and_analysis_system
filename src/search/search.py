import sys

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.search import search_google
from src.search import search_vk
from src.search import search_telegram
from src.search import search_youtube
from src.utils import logging_utils
from src.utils import utils
from src.storage import db, local_storage
from src.search import search_utils


# Setup logger
logger = logging_utils.setup_logger("search.py")


async def _search_google(task={}):
    """Handle Google search platform."""
    search_google_parameters = task.get('search_google_parameters', {})
    if not search_google_parameters.get('enabled', True):
        return []
    
    search_google_queries_obj = task.get('search_google_queries', {})
    
    # Concatenate all lists from the object into one full list
    search_google_queries = []
    for field_name, query_list in search_google_queries_obj.items():
        if isinstance(query_list, list):
            search_google_queries.extend(query_list)
    
    # Expand queries where 'query' field is an array
    expanded_google_queries = []
    for query_config in search_google_queries:
        query_field = query_config.get('query')
        if isinstance(query_field, list):
            # Create separate query config for each query in the array
            for single_query in query_field:
                expanded_config = query_config.copy()
                expanded_config['query'] = single_query
                expanded_google_queries.append(expanded_config)
        else:
            # Keep as-is if query is not an array
            expanded_google_queries.append(query_config)
    search_google_queries = expanded_google_queries
    
    # Resolve dates in Google queries
    search_google_queries = [search_utils.resolve_dates_in_parameters(q) for q in search_google_queries]
    
    # Search Google
    google_results_combined = []
    for idx, google_params in enumerate(search_google_queries):
        if isinstance(google_params, dict) and google_params.get('enabled', True):
            if google_params.get('use_mock_results', False):
                mock_path = google_params.get('mock_results_path', '')
                google_results = utils.load_mock_results(mock_path)
            else:
                google_results = await search_google.search_google(google_params)
            
            google_results_combined.extend(google_results)
    
    return google_results_combined


async def _search_vk(task={}):
    """Handle VK search platform."""
    search_vk_params = task.get('search_vk_parameters', {})
    if not search_vk_params.get('enabled', True):
        return []
    
    # Resolve dates in VK parameters
    search_vk_params = search_utils.resolve_dates_in_parameters(search_vk_params)
    
    if search_vk_params.get('use_mock_results', False):
        mock_path = search_vk_params.get('mock_results_path', '')
        return utils.load_mock_results(mock_path)
    
    return await search_vk.search_vk(search_vk_params)


async def _search_telegram(task={}):
    """Handle Telegram search platform."""
    telegram_params = task.get('search_telegram_parameters', {})
    if not telegram_params.get('enabled', True):
        return []
    
    # Resolve dates in Telegram parameters
    telegram_params = search_utils.resolve_dates_in_parameters(telegram_params)
    
    if telegram_params.get('use_mock_results', False):
        mock_path = telegram_params.get('mock_results_path', '')
        return utils.load_mock_results(mock_path)
    
    return await search_telegram.search_telegram(telegram_params)


async def _search_youtube(task={}):
    """Handle YouTube search platform."""
    youtube_params = task.get('search_youtube_parameters', {})
    if not youtube_params.get('enabled', True):
        return []
    
    # Resolve dates in YouTube parameters
    youtube_params = search_utils.resolve_dates_in_parameters(youtube_params)
    
    if youtube_params.get('use_mock_results', False):
        mock_path = youtube_params.get('mock_results_path', '')
        return utils.load_mock_results(mock_path)
    
    return await search_youtube.search_youtube(youtube_params)


async def search(task={}):
    """
    Unified search function that searches across all enabled platforms and returns standardized results.
    
    Args:
        task (dict): Task configuration containing search parameters for each platform
        
    Returns:
        list: List of standardized search results from all platforms
    """
    logger.info(f"Starting search.py")

    # Check if using custom SQL query to search in cache
    if task.get("search_parameters", {}).get("search_in_cache_sql"):
        logger.debug(f"task.search_parameters.search_in_cache_sql is specified, using a SQL query to get search results")
        sql_query = task.get("search_parameters", {}).get("search_in_cache_sql")
        results = await db.get_posts_by_sql(sql_query)
    # Check if using mock results
    elif task.get("search_parameters", {}).get("use_mock_results", False):
        logger.debug(f"task.search_parameters.use_mock_results is true, using mock results to get search results")
        mock_path = task.get("search_parameters", {}).get("mock_results_path")
        results = utils.load_mock_results(mock_path)
    else:
        # Search across all platforms
        results = []
    
        # Google Search
        google_results = await _search_google(task)
        results.extend(google_results)
        
        # VK Search
        vk_results = await _search_vk(task)
        results.extend(vk_results)
        
        # Telegram Search
        telegram_results = await _search_telegram(task)
        results.extend(telegram_results)
        
        # YouTube Search
        youtube_results = await _search_youtube(task)
        results.extend(youtube_results)
    
    # Normalize results
    results = search_utils.normalize_results(results)

    # Remove duplicate results
    results = search_utils.remove_duplicate_results(results)

    # Determine post types
    results = search_utils.determine_post_types(results)

    # Filter out unwanted results
    results = search_utils.filter_unwanted_results(results)
    
    # Save results locally before filtering
    if task.get("storage_parameters", {}).get("save_search_results", True):
        local_storage.save_results_locally(results, "search_results")
    
    # Filter results that are already in the database if enabled
    results = await search_utils.filter_cached_results(results, task)

    # Filter results by enabled post types and limit by max_results_per_post_type per post type
    results = search_utils.filter_by_post_types_and_limit(results, task)
    
    # Filter results by score
    score_filter = task.get("search_parameters", {}).get("score_filter")
    if score_filter:
        results = [r for r in results if 'score' not in r or r.get("score") in score_filter]
        logger.info(f"Filtered results by score. Total number of search results after filtering: {len(results)}")
    
    logger.info(f"Finished 'search.py'. Total number of search results: {len(results)}")
    return results