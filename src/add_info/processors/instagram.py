"""
Instagram processor module for handling Instagram posts and reels.
"""
import asyncio
import sys
import os
import json
import aiohttp
import re
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import dotenv

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.storage import db
from src.utils import logging_utils

# Setup logger
logger = logging_utils.setup_logger('instagram.py')

# Load environment variables
dotenv.load_dotenv()

async def get_instagram_media_info(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch Instagram media information (post or reel) by URL.
    
    Args:
        url: Instagram post or reel URL
        
    Returns:
        Dictionary with media information or None if request failed
    """
    
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://instagram-looter2.p.rapidapi.com/post", 
            headers={
                "x-rapidapi-host": "instagram-looter2.p.rapidapi.com",
                "x-rapidapi-key": os.getenv("RAPIDAPI_API_KEY")
            }, 
            params={
                "url": url
            }
        ) as media_api_response:
            media_api_response.raise_for_status()

            media_api_data = await media_api_response.json()
            
            return media_api_data

async def add_profile_info(post_info: Dict[str, Any], task: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Parse Instagram profile information from a content info object and add it to the object.
    
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
        cached_profile_info = {}
        raw_profile_info = {}
        should_update_cache = True  # Default to updating cache

        # Check for cached profile info first if enabled
        if use_profile_cache:
            cached_profile_info = await db.get_profile(post_info['profile_url'], refresh_profile_data)
            if cached_profile_info and 'raw_profile_info' in cached_profile_info:
                logger.debug(f"Raw profile info cache hit. Profile url: {post_info['profile_url']}")
                raw_profile_info = cached_profile_info.pop('raw_profile_info')
                should_update_cache = False
                    
        # If no cached profile info, fetch it
        if not raw_profile_info or ('Ошибка' in json.dumps(cached_profile_info, ensure_ascii=False) and refetch_profile_with_errors):
            logger.debug(f"Fetching raw profile info. Url: {post_info['profile_url']}")
            async with aiohttp.ClientSession() as session:
                username = re.match(r"https://instagram.com/([^/]+)/?", post_info['profile_url']).group(1)

                async with session.get(
                    "https://instagram-looter2.p.rapidapi.com/profile2",
                    headers={
                        "x-rapidapi-host": "instagram-looter2.p.rapidapi.com",
                        "x-rapidapi-key": os.getenv("RAPIDAPI_API_KEY")
                    },
                    params={
                        "username": username
                    }
                ) as profile_api_response:
                    profile_api_response.raise_for_status()
                    raw_profile_info = await profile_api_response.json()
            should_update_cache = True

        # Check if profile exists
        if raw_profile_info and not raw_profile_info.get('status', True):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info

        # Extract profile name
        try:
            profile_info["profile_name"] = raw_profile_info["full_name"]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram profile name. Url: {post_info['profile_url']}", e)
            profile_info["profile_name"] = f"Ошибка {error_info}"

        # Extract profile description
        try:
            profile_info["profile_description"] = raw_profile_info["biography"]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram profile description. Url: {post_info['profile_url']}", e)
            profile_info["profile_description"] = f"Ошибка {error_info}"

        # Extract profile subscribers count
        try:
            profile_info["profile_subscribers_count"] = raw_profile_info["follower_count"]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram profile subscribers count. Url: {post_info['profile_url']}", e)
            profile_info["profile_subscribers_count"] = f"Ошибка {error_info}"

        # Extract profile links
        try:
            if "bio_links" in raw_profile_info:
                profile_info["profile_links"] = raw_profile_info["bio_links"]
            else:
                profile_info["profile_links"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram profile links. Url: {post_info['profile_url']}", e)
            profile_info["profile_links"] = f"Ошибка {error_info}"

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error parsing Instagram profile. Profile url: {post_info['profile_url']}", e)
        post_info['debug_info']['add_profile_info_error_info'] = error_info
        post_info['debug_info']['add_profile_info_error_message'] = str(e)
        
    # Cache the profile info with the raw profile info if enabled
    if (update_profile_cache and should_update_cache) or force_update_profile_cache:
        await db.save_profile(post_info['profile_url'], {'raw_profile_info': raw_profile_info, **profile_info})

    # Add final profile info without raw_profile_info to the post_info
    post_info['profile_info'] = profile_info

    return post_info

async def get_instagram_post_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process an Instagram post asynchronously."""
    
    # Extract parameters from task
    add_info_parameters = task.get("add_info_parameters", {})
    use_post_cache = add_info_parameters.get("use_post_cache", True)
    refetch_post_with_errors = add_info_parameters.get("refetch_post_with_errors", False)
    
    # Initialize an empty post_info
    post_info = {
        'debug_info': {}
    }
    cached_post_info = {}
    raw_post_info = {}

    try:
        # Check for cached post info first if enabled
        if use_post_cache:
            cached_post_info = await db.get_post(result['url'])
            if cached_post_info and 'raw_post_info' in cached_post_info.get('post_info', {}):
                logger.debug(f"Raw post info cache hit. Url: {result['url']}")
                raw_post_info = cached_post_info['post_info'].pop('raw_post_info')

        if not raw_post_info or ('Ошибка' in json.dumps(cached_post_info.get('post_info', {}), ensure_ascii=False) and refetch_post_with_errors):
            logger.debug(f"Fetching raw post info. Url: {result['url']}")
            raw_post_info = await get_instagram_media_info(result['url'])
            post_info['should_update_cache'] = True

        if any([substring in raw_post_info.get('errorMessage', '').lower() for substring in ['not exist', 'private']]):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info

        # Extract publication date
        try:
            timestamp = raw_post_info["taken_at_timestamp"]
            date_string = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            post_info['publication_date'] = date_string
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram post publication date. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"
        
        # Extract description
        try:
            edges = raw_post_info["edge_media_to_caption"]["edges"]
            if len(edges) > 0:
                post_info['text'] = edges[0]["node"]["text"] or ""
            else:
                post_info['text'] = ""
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram post description. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"
        
        # Extract likes count
        try:
            likes_count = raw_post_info["edge_media_preview_like"]["count"]
            if likes_count == -1:
                post_info['likes_count'] = "Скрыто"
            else:
                post_info['likes_count'] = likes_count
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram post likes count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"
        
        # Extract comments count
        try:
            if "edge_media_preview_comment" in raw_post_info and "count" in raw_post_info["edge_media_preview_comment"]:
                post_info['comments_count'] = raw_post_info["edge_media_preview_comment"]["count"]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram post comments count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['comments_count'] = f"Ошибка {error_info}"
        
        # Extract profile information
        try:
            username = raw_post_info["owner"]["username"]
            post_info['profile_url'] = f"https://instagram.com/{username}/"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram post profile url. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_instagram_post_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info

async def get_instagram_reel_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process an Instagram reel asynchronously."""
    
    # Extract parameters from task
    add_info_parameters = task.get("add_info_parameters", {})
    use_post_cache = add_info_parameters.get("use_post_cache", True)
    refetch_post_with_errors = add_info_parameters.get("refetch_post_with_errors", False)
    
    # Initialize an empty post_info
    post_info = {
        'debug_info': {}
    }
    cached_post_info = {}
    raw_post_info = {}

    try:
        # Check for cached post info first if enabled
        if use_post_cache:
            cached_post_info = await db.get_post(result['url'])
            if cached_post_info and 'raw_post_info' in cached_post_info.get('post_info', {}):
                logger.debug(f"Raw post info cache hit. Url: {result['url']}")
                raw_post_info = cached_post_info['post_info'].pop('raw_post_info')

        if not raw_post_info or ('Ошибка' in json.dumps(cached_post_info.get('post_info', {}), ensure_ascii=False) and refetch_post_with_errors):
            logger.debug(f"Fetching raw post info. Url: {result['url']}")
            raw_post_info = await get_instagram_media_info(result['url'])
            post_info['should_update_cache'] = True

        if any([substring in raw_post_info.get('errorMessage', '').lower() for substring in ['not exist', 'private']]):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info

        # Extract publication date
        try:
            timestamp = raw_post_info["taken_at_timestamp"]
            date_string = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            post_info['publication_date'] = date_string
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram reel publication date. Reel url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"
        
        # Extract description
        try:
            edges = raw_post_info["edge_media_to_caption"]["edges"]
            if len(edges) > 0:
                post_info['text'] = edges[0]["node"]["text"] or ""
            else:
                post_info['text'] = ""
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram reel description. Reel url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"
        
        # Extract view count
        try:
            post_info['views_count'] = raw_post_info["video_play_count"]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram reel view count. Reel url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['views_count'] = f"Ошибка {error_info}"
        
        # Extract likes count
        try:
            likes_count = raw_post_info["edge_media_preview_like"]["count"]
            if likes_count == -1:
                post_info['likes_count'] = "Скрыто"
            else:
                post_info['likes_count'] = likes_count
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram reel likes count. Reel url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"
        
        # Extract comments count - try different possible fields
        try:
            # Try edge_media_preview_comment first
            if "edge_media_preview_comment" in raw_post_info and "count" in raw_post_info["edge_media_preview_comment"]:
                post_info['comments_count'] = raw_post_info["edge_media_preview_comment"]["count"]
            # Then try edge_media_to_parent_comment
            elif "edge_media_to_parent_comment" in raw_post_info and "count" in raw_post_info["edge_media_to_parent_comment"]:
                post_info['comments_count'] = raw_post_info["edge_media_to_parent_comment"]["count"]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram reel comments count. Reel url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['comments_count'] = f"Ошибка {error_info}"
        
        # Extract profile info
        try:
            username = raw_post_info["owner"]["username"]
            post_info['profile_url'] = f"https://instagram.com/{username}/"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Instagram reel profile info. Reel url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"
        
        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_instagram_reel_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info