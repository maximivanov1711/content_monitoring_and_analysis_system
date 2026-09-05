import asyncio
import sys
import json
import uuid

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from add_score import add_score
from src.storage import db
from src.utils import logging_utils
from src.add_subtitles.parse_subtitles import parse_subtitles
from src.add_subtitles.transcribe_subtitles import transcribe_subtitles
from src.add_subtitles import add_subtitles_utils

# Setup logger
logger = logging_utils.setup_logger('add_subtitles.py')

# Define constants
BATCH_SIZE = 10 
REQUESTS_DELAY = 1

# Types of posts that should be processed with parse_subtitles
ONLY_PARSE_POST_TYPES = [
    "tiktok_video"
]
ONLY_TRANSCRIBE_POST_TYPES = [
    "telegram_post",
    "instagram_reels",
    "twitch_video",
    "twitch_stream",
    "dzen_long_video",
    "dzen_short_video",
]
PARSE_AND_TRANSCRIBE_POST_TYPES = [
    "youtube_video",
    "youtube_shorts",
    "vk_long_video",
    "vk_short_video",
]


async def process_single_result(result, semaphore, task={}):
    """
    Process a single result for subtitles.

    Args:
        result: Dictionary containing the result data
        semaphore: Semaphore for controlling concurrency
        task: Task dictionary containing processing parameters
    
    Returns:
        Dictionary containing the result data with subtitles data
    """
    try:
        # Extract parameters from task
        use_post_cache = task.get("add_subtitles_parameters", {}).get("use_post_cache", True)
        update_post_cache = task.get("add_subtitles_parameters", {}).get("update_post_cache", True)
        fields_to_update = task.get("add_subtitles_parameters", {}).get("fields_to_update", None)

        # Skip if post type is not supported for subtitles
        subtitles_post_types = (
            ONLY_PARSE_POST_TYPES + 
            ONLY_TRANSCRIBE_POST_TYPES + 
            PARSE_AND_TRANSCRIBE_POST_TYPES
        )
        if result['post_type'] not in subtitles_post_types:
            logging_utils.log_warning(logger, f"Result post type is not supported for adding subtitles, skipping to the next result. Result url: {result['url']}, result post type: {result['post_type']}")
            return result
        
        # Check cache first if enabled (outside semaphore)
        if use_post_cache:
            cached_post_info = await db.get_post(result['url'])
            if cached_post_info and cached_post_info.get('subtitles_info', {}).get('subtitles'):
                logger.debug(f"Subtitles data cache hit. Result url: {result['url']}")
                result['subtitles_info'] = cached_post_info['subtitles_info']
        
        if not 'subtitles' in result.get('subtitles_info', {}):
            # Only use semaphore for actual subtitle processing
            async with semaphore:
                # Wait for request delay
                await asyncio.sleep(REQUESTS_DELAY)

                # Add subtitles data to result
                if result['post_type'] in ONLY_PARSE_POST_TYPES:
                    logger.debug(f"Using parse_subtitles. Result url: {result['url']}")
                    try:
                        result['subtitles_info'] = await parse_subtitles(result, task)
                    except Exception as e:
                        logging_utils.log_warning(logger, f"Error using parse_subtitles. Using transcribe_subtitles instead. post url: {result['url']}")
                        result = await transcribe_subtitles(result, task)
                elif result['post_type'] in ONLY_TRANSCRIBE_POST_TYPES:
                    logger.debug(f"Using transcribe_subtitles. Result url: {result['url']}")
                    result = await transcribe_subtitles(result, task)
                elif result['post_type'] in PARSE_AND_TRANSCRIBE_POST_TYPES:
                    logger.debug(f"First trying parse_subtitles. Result url: {result['url']}")
                    result['subtitles_info'] = await parse_subtitles(result, task)
                    
                    if not result['subtitles_info']:
                        logger.debug(f"No subtitles data returned from parse_subtitles, using transcribe_subtitles. Result url: {result['url']}")
                        result = await transcribe_subtitles(result, task)
        
        # Check subtitle length and upload to GitHub Gist if needed
        if result.get('subtitles_info') and 'subtitles' in result['subtitles_info']:
            if len(result['subtitles_info']['subtitles']) > 40000:
                logger.info(f"Subtitles length exceeds 40000 characters, uploading to GitHub Gist. Result url: {result['url']}, subtitles length: {len(result['subtitles_info']['subtitles'])}")
                
                # Upload to GitHub Gist
                gist_url = await add_subtitles_utils.upload_to_github_gist(
                    result['subtitles_info']['subtitles'], 
                    f"subtitles_{uuid.uuid4()}.txt", 
                    f"Subtitles for {result['url']}"
                )
                if gist_url:
                    result['subtitles_info']['subtitles_url'] = gist_url

        # Update cache if we have new data and cache update is enabled (outside semaphore)
        if update_post_cache:
            await db.save_post(result['url'], result, fields_to_update=fields_to_update)

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error processing subtitles. Result url: {result['url']}", e)
        result['debug_info']['errors'].append(error_info)

    # Add score to result
    if task.get("add_score_parameters", {}).get("add_score_in_add_subtitles", True):
        result['score'] = await add_score.calculate_score(result)

    return result


async def add_subtitles(results, task={}):
    """
    Add subtitles to search results.
    
    Args:
        results: List of search result dictionaries
        task: Dictionary containing processing parameters (optional)
    
    Returns:
        List of search results enhanced with subtitle information
    """
    try:        
        score_filter = task.get("add_subtitles_parameters", {}).get("score_filter")
        if score_filter:
            indices_to_process = [i for i, r in enumerate(results) if r.get('score') in score_filter]
            logger.info(f"Filtered results by score. Score filter: {score_filter}, number of results to process: {len(indices_to_process)}, total results: {len(results)}")
        else:
            indices_to_process = list(range(len(results)))

        semaphore = asyncio.Semaphore(BATCH_SIZE)

        to_process = [results[i] for i in indices_to_process]
        processed_results = await asyncio.gather(*[process_single_result(r, semaphore, task) for r in to_process], return_exceptions=True)

        final_results = []
        processed_pointer = 0
        indices_set = set(indices_to_process)
        for i, r in enumerate(results):
            if i in indices_set:
                final_results.append(processed_results[processed_pointer])
                processed_pointer += 1
            else:
                final_results.append(r)

        return final_results

    except Exception as e:
        logging_utils.log_error(logger, f"Error in add_subtitles.add_subtitles()", e)
        return results