"""
TikTok processor module for handling TikTok videos and photos.
"""
import sys
import os
import asyncio
import aiohttp
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import dotenv
import json

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.storage import db
from src.utils import logging_utils
from src.utils import utils

# Setup logger
logger = logging_utils.setup_logger('tiktok.py')

# Load environment variables
dotenv.load_dotenv()

async def get_tiktok_media_info(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch TikTok media information by URL.
    
    Args:
        url: TikTok video or photo URL
        
    Returns:
        Dictionary with media information or None if request failed
    """
    try:
        # Extract video ID from URL
        video_id = url.split('/')[-1]
        # Remove query parameters if present
        if '?' in video_id:
            video_id = video_id.split('?')[0]

        max_retries = 10
        wait_time = 0.5
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://tiktok-api23.p.rapidapi.com/api/post/detail",
                        headers={
                            "x-rapidapi-host": "tiktok-api23.p.rapidapi.com",
                            "x-rapidapi-key": os.getenv("RAPIDAPI_API_KEY")
                        },
                        params={
                            "videoId": video_id
                        }
                    ) as api_response:
                        api_response.raise_for_status()
                        # Check if response has content
                        if api_response.status == 204:
                            if attempt < max_retries - 1:
                                logging_utils.log_error(logger, f"Received 204 No Content for URL: {url}, attempt {attempt+1}/{max_retries}, waiting {wait_time}s before retry")
                                await asyncio.sleep(wait_time)
                                wait_time += 0.2
                                continue
                            else:
                                return {"error": "No content returned from API after maximum retries", "status": 204}
                        
                        api_data = await api_response.json()
                        return api_data
            except aiohttp.ClientResponseError as e:
                if attempt < max_retries - 1:
                    logging_utils.log_warning(logger, f"Request failed for URL: {url}, attempt {attempt+1}/{max_retries}, waiting {wait_time}s before retry: {str(e)}")
                    await asyncio.sleep(wait_time)
                    wait_time += 0.5
                else:
                    raise
            except Exception as e:
                if attempt < max_retries - 1:
                    logging_utils.log_warning(logger, f"Error processing URL: {url}, attempt {attempt+1}/{max_retries}, waiting {wait_time}s before retry: {str(e)}", e)
                    await asyncio.sleep(wait_time)
                    wait_time += 0.5
                else:
                    raise
    
    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error processing TikTok media", e)
        logging_utils.log_error(logger, f"Error processing TikTok media: {str(e)} (Error ID: {error_info})")
        return None

async def add_profile_info(post_info: Dict[str, Any], task: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Parse TikTok profile information from a content info object and add it to the object.
    
    Args:
        post_info: The content info dictionary containing profile_url and unique_id fields
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
        unique_id = post_info.get('unique_id')
        profile_url = post_info.get('profile_url')
        
        # Check for cached profile info first if enabled
        raw_profile_info = None
        cached_profile_info = None
        should_update_cache = True  # Default to updating cache
        if use_profile_cache:
            cached_data = await db.get_profile(profile_url, refresh_profile_data)
            if cached_data and 'raw_profile_info' in cached_data:
                logger.debug(f"Raw profile info cache hit. Url: {profile_url}")
                raw_profile_info = cached_data['raw_profile_info']
                cached_profile_info = cached_data.copy()
                cached_profile_info.pop('raw_profile_info', None)
                should_update_cache = False
                    
        # If no cached profile info, fetch it
        if raw_profile_info is None or ('Ошибка' in json.dumps(cached_profile_info, ensure_ascii=False) and refetch_profile_with_errors):
            logger.debug(f"Fetching raw profile info. Url: {profile_url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://tiktok-api23.p.rapidapi.com/api/user/info",
                    headers={
                        "x-rapidapi-host": "tiktok-api23.p.rapidapi.com",
                        "x-rapidapi-key": os.getenv("RAPIDAPI_API_KEY")
                    },
                    params={
                        "uniqueId": unique_id
                    }
                ) as profile_api_response:
                    profile_api_response.raise_for_status()
                    raw_profile_info = await profile_api_response.json()
            should_update_cache = True

        # Extract profile name
        try:
            user_data = raw_profile_info["userInfo"]["user"]
            profile_info["profile_name"] = f"{unique_id} ({user_data['nickname']})"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok profile name. Url: {profile_url}", e)
            profile_info["profile_name"] = f"Ошибка {error_info}"

        # Extract profile description
        try:
            profile_info["profile_description"] = user_data["signature"] or ""
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok profile description. Url: {profile_url}", e)
            profile_info["profile_description"] = f"Ошибка {error_info}"

        # Extract profile subscribers count
        try:
            stats_data = raw_profile_info["userInfo"]["stats"]
            profile_info["profile_subscribers_count"] = stats_data["followerCount"]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok profile subscribers count. Url: {profile_url}", e)
            profile_info["profile_subscribers_count"] = f"Ошибка {error_info}"

        # Extract profile links
        try:
            profile_info["profile_links"] = []
            if "bioLink" in user_data:
                profile_info["profile_links"].append(user_data["bioLink"]["link"])
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok profile links. Url: {profile_url}", e)
            profile_info["profile_links"].append(f"Ошибка {error_info}")

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error parsing TikTok profile. Profile url: {profile_url}", e)
        post_info['debug_info']['add_profile_info_error_info'] = error_info
        post_info['debug_info']['add_profile_info_error_message'] = str(e)
        
    # Cache the profile info with the raw profile info if enabled
    if (update_profile_cache and should_update_cache) or force_update_profile_cache:
        await db.save_profile(profile_url, {'raw_profile_info': raw_profile_info, **profile_info})

    # Add final profile info without raw_profile_info to the post_info
    post_info['profile_info'] = profile_info

    return post_info

async def get_tiktok_video_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Process a TikTok video asynchronously."""
    
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

        # If no cached post info, fetch it
        if raw_post_info is None or ('Ошибка' in json.dumps(cached_post_info, ensure_ascii=False) and refetch_post_with_errors):
            logger.debug(f"Fetching raw video info. Url: {result['url']}")
            raw_post_info = await get_tiktok_media_info(result['url'])
            post_info['should_update_cache'] = True

        # Handle non-zero status code
        if (
            isinstance(raw_post_info, dict)
            and 'statusCode' in raw_post_info
            and raw_post_info['statusCode'] != 0
        ):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info

        # Extract item info for easier access
        item_info = raw_post_info.get("itemInfo", {}).get("itemStruct", {})
        
        # Extract publication date
        try:
            create_time = item_info.get("createTime")
            date_string = datetime.fromtimestamp(int(create_time)).strftime('%Y-%m-%d')
            post_info['publication_date'] = date_string
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok video publication date. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"
        
        # Extract description
        try:
            post_info['text'] = item_info.get("desc", "")
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok video description. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"
        
        # Extract stats
        stats = item_info.get("stats", {})
        
        # Extract view count
        try:
            post_info['views_count'] = int(stats.get("playCount", 0))
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok video view count. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['views_count'] = f"Ошибка {error_info}"
        
        # Extract likes count
        try:
            post_info['likes_count'] = int(stats.get("diggCount", 0))
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok video likes count. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"
        
        # Extract comments count
        try:
            post_info['comments_count'] = int(stats.get("commentCount", 0))
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok video comments count. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['comments_count'] = f"Ошибка {error_info}"
        
        # Extract profile information
        try:
            author = item_info.get("author", {})
            unique_id = author.get("uniqueId", "")
            post_info['unique_id'] = unique_id
            post_info['profile_url'] = f"https://tiktok.com/@{unique_id}/"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok video profile info. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_tiktok_video_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info

async def get_tiktok_photo_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Process a TikTok photo asynchronously."""
    
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

        # If no cached post info, fetch it
        if raw_post_info is None or ('Ошибка' in json.dumps(cached_post_info, ensure_ascii=False) and refetch_post_with_errors):
            logger.debug(f"Fetching raw photo info. Url: {result['url']}")
            raw_post_info = await get_tiktok_media_info(result['url'])
            post_info['should_update_cache'] = True

        # Handle non-zero status code
        if (
            isinstance(raw_post_info, dict)
            and 'statusCode' in raw_post_info
            and raw_post_info['statusCode'] != 0
        ):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info

        # Extract item info for easier access
        item_info = raw_post_info.get("itemInfo", {}).get("itemStruct", {})
        
        # Extract publication date
        try:
            create_time = item_info.get("createTime")
            date_string = datetime.fromtimestamp(int(create_time)).strftime('%Y-%m-%d')
            post_info['publication_date'] = date_string
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok photo publication date. Photo url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"
        
        # Extract description
        try:
            post_info['text'] = item_info.get("desc", "")
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok photo description. Photo url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"

        # Extract title from imagePost
        try:
            image_post = item_info.get("imagePost", {})
            if image_post:
                post_info['title'] = image_post.get("title", "")
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok photo title. Photo url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['title'] = f"Ошибка {error_info}"
        
        # Extract stats
        stats = item_info.get("stats", {})
        
        # Extract view count
        try:
            post_info['views_count'] = int(stats.get("playCount", 0))
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok photo view count. Photo url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['views_count'] = f"Ошибка {error_info}"
        
        # Extract likes count
        try:
            post_info['likes_count'] = int(stats.get("diggCount", 0))
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok photo likes count. Photo url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"
        
        # Extract comments count
        try:
            post_info['comments_count'] = int(stats.get("commentCount", 0))
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok photo comments count. Photo url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['comments_count'] = f"Ошибка {error_info}"
        
        # Extract profile information
        try:
            author = item_info.get("author", {})
            unique_id = author.get("uniqueId", "")
            post_info['unique_id'] = unique_id
            post_info['profile_url'] = f"https://tiktok.com/@{unique_id}/"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting TikTok photo profile info. Photo url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_tiktok_photo_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info 