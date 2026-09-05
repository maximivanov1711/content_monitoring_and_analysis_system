"""
Telegram processor module for handling Telegram posts.
"""
import sys
import os
import copy
from typing import Dict, Any, Tuple
from datetime import datetime
import dotenv
import aiohttp
from urlextract import URLExtract
import json

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.storage import db
from src.utils import logging_utils
from src.utils import utils

# Setup logger
logger = logging_utils.setup_logger('telegram.py')

# Initialize URL extractor
extractor = URLExtract()

# Load environment variables
dotenv.load_dotenv()

async def add_profile_info(post_info: Dict[str, Any], task: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Parse Telegram profile information from a content info object and add it to the object.
    
    Args:
        post_info: The content info dictionary containing a profile_url field
        task: The task configuration containing processing parameters
        
    Returns:
        The original post_info dictionary with added profile information
    """
    # Extract parameters from task
    add_info_parameters = task.get("add_info_parameters", {})
    use_profile_cache = add_info_parameters.get("use_profile_cache", True)
    update_profile_cache = add_info_parameters.get("update_profile_cache", True)
    force_update_profile_cache = add_info_parameters.get("force_update_profile_cache", False)
    refetch_profile_with_errors = add_info_parameters.get("refetch_profile_with_errors", False)
    refresh_profile_data = add_info_parameters.get("refresh_profile_data", False)
    
    # Initialize an empty profile_info
    profile_info = {}
    
    try:        
        # Check for cached profile info first if enabled
        raw_profile_info = None
        cached_profile_info = None
        should_update_cache = True  # Default to updating cache
        if use_profile_cache:
            cached_data = await db.get_profile(post_info['profile_url'], refresh_profile_data)
            if cached_data and 'raw_profile_info' in cached_data:
                logger.debug(f"Raw profile info cache hit. Url: {post_info['profile_url']}")
                raw_profile_info = cached_data['raw_profile_info']
                cached_profile_info = cached_data.copy()
                cached_profile_info.pop('raw_profile_info', None)
                should_update_cache = False
                    
        # If no cached profile info, fetch it
        if raw_profile_info is None or ('Ошибка' in json.dumps(cached_profile_info, ensure_ascii=False) and refetch_profile_with_errors):
            # Extract channel name from profile URL
            channel_name = post_info['profile_url'].split('/')[-1]
            
            url = f"https://telegram-channel.p.rapidapi.com/channel/info"
            headers = {
                'x-rapidapi-host': 'telegram-channel.p.rapidapi.com',
                'x-rapidapi-key': os.getenv('RAPIDAPI_API_KEY')
            }
            params = {
                'channel': channel_name
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    response.raise_for_status()
                    raw_profile_info = await response.json()
            should_update_cache = True

        # Handle case where API returns error message about unable to fetch channel info
        if raw_profile_info and 'unable to fetch' in raw_profile_info.get('err_msg', ''):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info

        # Extract profile name
        try:
            profile_info["profile_name"] = raw_profile_info['title']
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Telegram profile name. Url: {post_info['profile_url']}", e)
            profile_info["profile_name"] = f"Ошибка {error_info}"

        # Extract profile description
        try:
            profile_info["profile_description"] = raw_profile_info['description']
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Telegram profile description. Url: {post_info['profile_url']}", e)
            profile_info["profile_description"] = f"Ошибка {error_info}"

        # Extract URLs from profile description
        try:
            profile_info["profile_links"] = extractor.find_urls(profile_info["profile_description"])
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting URLs from Telegram profile description. Url: {post_info['profile_url']}", e)
            profile_info["profile_links"] = f"Ошибка {error_info}"

        # Extract profile subscribers count
        try:
            subscribers = raw_profile_info['subscribers']
            parsed_subscribers = utils.parse_number(subscribers)
            if isinstance(parsed_subscribers, int):
                profile_info["profile_subscribers_count"] = parsed_subscribers
            else:
                profile_info["profile_subscribers_count"] = subscribers
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Telegram profile subscribers count. Url: {post_info['profile_url']}", e)
            profile_info["profile_subscribers_count"] = f"Ошибка {error_info}"

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error parsing Telegram profile. Profile url: {post_info['profile_url']}", e)
        post_info['debug_info']['add_profile_info_error_info'] = error_info
        post_info['debug_info']['add_profile_info_error_message'] = str(e)
        
    # Cache the profile info with the raw profile info if enabled
    if (update_profile_cache and should_update_cache) or force_update_profile_cache:
        await db.save_profile(post_info['profile_url'], {'raw_profile_info': raw_profile_info, **profile_info})

    # Add final profile info without raw_profile_info to the post_info
    post_info['profile_info'] = profile_info

    return post_info

async def get_telegram_post_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Process a Telegram post asynchronously."""
    
    # Extract parameters from task
    add_info_parameters = task.get("add_info_parameters", {})
    use_post_cache = add_info_parameters.get("use_post_cache", True)
    refetch_post_with_errors = add_info_parameters.get("refetch_post_with_errors", False)
    
    # Initialize an empty post_info
    post_info = {
        'debug_info': {}
    }
    raw_post_info = None
    cached_post_info = None

    try:
        # Check for cached post info first if enabled
        if use_post_cache:
            cached_post = await db.get_post(result['url'])
            if cached_post and 'raw_post_info' in cached_post.get('post_info', ''):
                logger.debug(f"Raw post info cache hit. Url: {result['url']}")
                cached_post_info = cached_post['post_info'].copy()
                raw_post_info = cached_post['post_info']['raw_post_info']
                cached_post_info.pop('raw_post_info', None)

        if raw_post_info is None or ('Ошибка' in json.dumps(cached_post_info, ensure_ascii=False) and refetch_post_with_errors):
            raw_post_info = copy.deepcopy(result)
            post_info['should_update_cache'] = True

        if raw_post_info.get('is_deleted', False):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info

        # Extract publication date
        try:
            timestamp = raw_post_info["date"]
            date_string = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            post_info['publication_date'] = date_string
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Telegram post publication date. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"
        
        # Extract text content
        try:
            post_info['text'] = raw_post_info['text']
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Telegram post text. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"
        
        # Extract links
        try:
            post_info['links'] = [link['target_url'] for link in raw_post_info['links']]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Telegram post links. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['links'] = f"Ошибка {error_info}"
        
        # Extract views count
        try:
            post_info['views_count'] = raw_post_info['stats']['views']
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Telegram post views count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['views_count'] = f"Ошибка {error_info}"
        
        # Extract likes count (reactions in Telegram)
        try:
            post_info['likes_count'] = raw_post_info['stats']['reactions']
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Telegram post likes count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"
        
        # Extract comments count
        try:
            post_info['comments_count'] = raw_post_info['stats']['comments']
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Telegram post comments count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['comments_count'] = f"Ошибка {error_info}"
        
        # Extract profile URL
        try:
            post_info['profile_url'] = '/'.join(result['url'].split('/')[:4])
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Telegram post profile URL. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_telegram_post_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info
