"""
Main module for getting content info for search results.
"""

import asyncio
from typing import Dict, List, Any
import sys

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils
from src.utils import utils
from src.add_info.processors import instagram, youtube, tiktok, vk, twitch, dzen, telegram
from src.storage import db
from src.add_score import add_score
from src.add_info import add_info_utils 


# Setup logger
logger = logging_utils.setup_logger(prefix="add_info.py")

# Map content types to their processor functions
PROCESSORS = {
    "instagram_post": instagram.get_instagram_post_info,
    "instagram_reels": instagram.get_instagram_reel_info,
    "youtube_video": youtube.get_youtube_video_info,
    "youtube_shorts": youtube.get_youtube_shorts_info,
    "youtube_post": youtube.get_youtube_post_info,
    "tiktok_video": tiktok.get_tiktok_video_info,
    "tiktok_photo": tiktok.get_tiktok_photo_info,
    "vk_post": vk.get_vk_post_info,
    "vk_long_video": vk.get_vk_video_info,
    "vk_short_video": vk.get_vk_video_info,
    "twitch_video": twitch.get_twitch_clip_info,
    "twitch_stream": twitch.get_twitch_stream_info,
    "dzen_article": dzen.get_dzen_article_info,
    "dzen_news": dzen.get_dzen_news_info,
    "dzen_short_video": dzen.get_dzen_short_video_info,
    "dzen_long_video": dzen.get_dzen_long_video_info,
    "dzen_post": dzen.get_dzen_post_info,
    "telegram_post": telegram.get_telegram_post_info,
}


async def process_result(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Process a search result based on its content type asynchronously.
    
    Args:
        search_result: The search result dictionary, containing at least a 'url' field
        task: The task configuration containing processing parameters

    Returns:
        A dictionary containing the processed post information
    """
    try:
        # Extract parameters from task
        update_post_cache = task.get("add_info_parameters", {}).get("update_post_cache", True)
        force_update_post_cache = task.get("add_info_parameters", {}).get("force_update_post_cache", False)
        force_skip_processing = task.get("add_info_parameters", {}).get("force_skip_processing", False)
        skip_with_post_info = task.get("add_info_parameters", {}).get("skip_with_post_info", False)
        fields_to_update = task.get("add_info_parameters", {}).get("fields_to_update", None)

        # Check if search result already has post_info or if processing should be skipped
        if ("post_info" in result and skip_with_post_info) or force_skip_processing:
            # Use existing post_info and merge with defaults
            post_info = result.get("post_info")
            raw_post_info = post_info.get("raw_post_info")
        else:
            # Send a warning if the post type cannot be determine
            if result['post_type'] not in PROCESSORS:
                logging_utils.log_warning(logger, f"Unknown post type '{result['post_type']}'. Result url: {result['url']}, returning default post_info")
                return result

            # Call the correct processor and add the post_info to the result object
            processor = PROCESSORS[result['post_type']]
            post_info, raw_post_info = await processor(result, task)

        # Merge extracted post_info with the default post_info
        result["post_info"].update(post_info)

        # Normalize URLs in links array if it exists
        if 'links' in result['post_info']:
            normalized_links = []
            for link in result['post_info']['links']:
                normalized_links.append(utils.normalize_url(link, remove_query_params=False))
            result['post_info']['links'] = normalized_links

        # Set profile types
        result['post_info']['is_excluded_profile'] = utils.is_excluded_profile(result['post_info'].get('profile_url', ''))
        result['post_info']['is_editor_profile'] = utils.is_editor_profile(result)

        # Calculate and add score
        if task.get("add_score_parameters", {}).get("add_score_in_add_info", True):
            result['score'] = await add_score.calculate_score(result)

        # Cache the final post object if force_update_post_cache is True or update_post_cache is True and post info was not found in cache
        if (update_post_cache and result['post_info'].get('should_update_cache', False)) or force_update_post_cache:
            logger.debug(f"Updating post cache. Result url: {result['url']}")
            # Add raw_post_info to the post cache
            post_cache = result.copy()
            post_cache["post_info"]["raw_post_info"] = raw_post_info
            await db.save_post(result['url'], post_cache, fields_to_update=fields_to_update)

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'add_info.process_result()'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)

    return result


async def process_batch_item_with_delay(result: Dict[str, Any], delay: float, task: Dict[str, Any] = {}) -> Dict[str, Any]:
    """Process a single batch item with an initial delay."""
    if delay > 0:
        await asyncio.sleep(delay)
    return await process_result(result, task)


async def process_platform_results(platform_results: List[Dict[str, Any]], platform: str, task: Dict[str, Any] = {}) -> List[Dict[str, Any]]:
    """Process results for a specific platform with platform-specific parameters."""
    
    # Extract parameters from task
    batch_settings = task.get("add_info_parameters", {}).get("batch_settings", {})
    platform_params = batch_settings.get(platform, {})
    batch_size = platform_params.get('batch_size', 1)
    delay_between_calls = platform_params.get('delay_between_calls', 5)
    delay_between_batches = platform_params.get('delay_between_batches', 0)
    
    # Calculate total number of batches
    total_batches = (len(platform_results) + batch_size - 1) // batch_size

    all_posts = []
    # Process each batch of results
    for batch_idx in range(total_batches):
        batch_start = batch_idx * batch_size
        batch_end = min(batch_start + batch_size, len(platform_results))
        current_batch = platform_results[batch_start:batch_end]
        
        # Process batch items concurrently with staggered delays
        batch_tasks = []
        for idx, result in enumerate(current_batch):
            delay = idx * delay_between_calls
            task_coro = process_batch_item_with_delay(result, delay, task)
            batch_tasks.append(task_coro)
        
        # Run all batch items concurrently
        batch_posts = await asyncio.gather(*batch_tasks)
        all_posts.extend(batch_posts)
        
        # Wait between batches (except after the last batch)
        if batch_idx < total_batches - 1:
            await asyncio.sleep(delay_between_batches)

    return all_posts


async def add_info(results: List[Dict[str, Any]], task: Dict[str, Any] = {}) -> List[Dict[str, Any]]:
    """
    Add content information to search results.
    
    Args:
        search_results: List of search result dictionaries, each containing at least a 'url' field
        task: Dictionary containing processing parameters
    
    Returns:
        List of search results enhanced with content information
    """
    try:  
        # Extract parameters from task
        use_mock_results = task.get("add_info_parameters", {}).get("use_mock_results", False)
        mock_results_path = task.get("add_info_parameters", {}).get("mock_results_path")
        start_date = task.get("add_info_parameters", {}).get("start_date")
        end_date = task.get("add_info_parameters", {}).get("end_date")

        # Check if using mock results
        if use_mock_results:
            mock_results = utils.load_mock_results(mock_results_path)

            logger.debug(f"Used mock results for 'add_info.py'. 'mock_results_path': {mock_results_path}")
            return mock_results

        # Group results by platform
        platform_groups = {}
        for idx, result in enumerate(results):
            post_type = result.get("post_type")
            platform = post_type.split("_")[0]
            if platform not in platform_groups:
                platform_groups[platform] = []
            platform_groups[platform].append(result)
        
        # Process each platform group with its specific parameters
        posts = []
        for platform, platform_search_results in platform_groups.items():
            # Process platform results one after another
            posts.extend(
                await process_platform_results(
                    platform_search_results,
                    platform,
                    task
                )
            )
        
        # Resolve date parameters if they exist
        if start_date:
            start_date = utils.resolve_date_parameter(start_date)
        if end_date:
            end_date = utils.resolve_date_parameter(end_date)
        
        # Filter posts by date if start_date or end_date is specified
        if start_date or end_date:
            filtered_posts = []
            for post in posts:
                if add_info_utils.should_include_post_by_date(post, start_date, end_date):
                    filtered_posts.append(post)
            return filtered_posts
        
        return posts
        
    except Exception as e:
        logging_utils.log_error(logger, "Error in add_info.add_info(), returning current results", e)
        return results