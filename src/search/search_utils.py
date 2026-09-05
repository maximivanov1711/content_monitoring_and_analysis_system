import sys

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import utils
from src.utils import logging_utils
from src.storage import db


# Setup logger
logger = logging_utils.setup_logger("search_utils.py")


def resolve_dates_in_parameters(parameters):
    """
    Resolve date parameters in search parameters, handling nested structures.
    
    Args:
        parameters: Search parameters dictionary or list
        
    Returns:
        dict/list: Parameters with resolved dates
    """
    resolved_params = parameters.copy()
    for key, value in resolved_params.items():
        if key in ["start_date", "end_date"] and value:
            resolved_params[key] = utils.resolve_date_parameter(value)
        elif key == "dates" and isinstance(value, list):
            resolved_dates = []
            for date_entry in value:
                if isinstance(date_entry, dict):
                    resolved_date_entry = date_entry.copy()
                    if "start_date" in resolved_date_entry:
                        resolved_date_entry["start_date"] = utils.resolve_date_parameter(resolved_date_entry["start_date"])
                    if "end_date" in resolved_date_entry:
                        resolved_date_entry["end_date"] = utils.resolve_date_parameter(resolved_date_entry["end_date"])
                    resolved_dates.append(resolved_date_entry)
                else:
                    resolved_dates.append(date_entry)
            resolved_params[key] = resolved_dates
    return resolved_params


def remove_duplicate_results(search_results):
    """Remove duplicates based on URL."""
    unique_results = []
    seen_urls = set()
    
    for result in search_results:
        url = result.get('url')
        if url and url not in seen_urls:
            unique_results.append(result)
            seen_urls.add(url)
    
    return unique_results


def normalize_results(results):
    """Normalize URLs and determine post types for all search results."""
    normalized_results = []
    for result in results:
        normalized_result = {
            'post_info': {
                'processed': False,
                'valid': True,
                'is_excluded_profile': False,
                'is_editor_profile': False,
                'profile_info': {},
                'debug_info': {}
            },
            'subtitles_info': {
            },
            'analysis_info': {
            },
            'debug_info': {
                'errors': []
            },
            **result,
            'url': utils.normalize_url(result['url']),
        }
        normalized_results.append(normalized_result)

    return normalized_results


def determine_post_types(results):
    """
    Determine the post type for all search results.
    """
    for result in results:
        result["post_type"] = utils.determine_post_type(result["url"])
    return results


def filter_unwanted_results(results):
    """Filter out unwanted results."""
    filtered_search_results = []
    for result in results:
        if "twitch" in result["post_type"] and result["url"].endswith("/clips"):
            continue
        filtered_search_results.append(result)
    return filtered_search_results


async def filter_cached_results(results, task={}):
    """Filter results that are already in the database if enabled."""
    filter_cached = task.get("search_parameters", {}).get("filter_cached", False)
    
    if not filter_cached or not results:
        return results
    
    logger.info(f"Filtering cached results enabled - checking {len(results)} URLs against database")
    
    # Get all URLs to check
    urls_to_check = [result["url"] for result in results]
    
    # Check which URLs already exist in the database
    existing_urls = await db.check_posts_exist(urls_to_check)
    
    # Filter out existing URLs
    filtered_results = [result for result in results if result["url"] not in existing_urls]
    
    logger.info(f"Filtered out {len(existing_urls)} cached results, {len(filtered_results)} remaining")
    return filtered_results


def filter_by_post_types_and_limit(results, task={}):
    """Filter by enabled post types and limit by max_results_per_post_type per post type."""
    enabled_post_types = task["enabled_post_types"]
    max_results_per_post_type = task.get("search_parameters", {}).get('max_results_per_post_type')
    
    # Group results by post_type
    post_type_groups = {}
    for result in results:
        if result["post_type"] in enabled_post_types:
            post_type = result["post_type"]
            if post_type not in post_type_groups:
                post_type_groups[post_type] = []
            post_type_groups[post_type].append(result)
    
    # Limit each post type to max_results_per_post_type and combine
    filtered_results = []
    for post_type, results in post_type_groups.items():
        if max_results_per_post_type is not None:
            limited_results = results[:max_results_per_post_type]
        else:
            limited_results = results
        filtered_results.extend(limited_results)
    
    return filtered_results