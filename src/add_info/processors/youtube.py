"""
YouTube processor module for handling YouTube videos, shorts, and posts.
"""
import sys
import os
import aiohttp
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import re
import urllib.parse
import random
import asyncio
import json

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]

from src.storage import db
from src.utils import utils, logging_utils

# Set up logging
logger = logging_utils.setup_logger(prefix='youtube.py')

async def get_youtube_video_raw_info(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch YouTube video information by URL using YT API.
    
    Args:
        url: YouTube video URL
        
    Returns:
        Dictionary with video information or None if request failed
    """
    try:
        if "/watch?v=" in url:
            video_id = url.split("/watch?v=")[1].split("&")[0]
        else:
            video_id = url.split("/shorts/")[1].split("?")[0]

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://yt-api.p.rapidapi.com/video/info",
                headers={
                    "x-rapidapi-host": "yt-api.p.rapidapi.com",
                    "x-rapidapi-key": os.getenv("RAPIDAPI_API_KEY")
                },
                params={
                    "id": video_id,
                    "extend": "2",
                }
            ) as response:
                response.raise_for_status()

                video_info = await response.json()
                
                return video_info
    except Exception as e:
        logging_utils.log_error(logger, f"Error fetching YouTube video raw info for {url}", e)
        return None

async def add_profile_info(post_info: Dict[str, Any], task: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Fetch YouTube channel information and add it to the given post_info.

    Args:
        post_info: Dict that must include a 'profile_url' key (e.g. "https://www.youtube.com/channel/<id>")
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
        profile_url = post_info['profile_url']
        profile_username = "@" + profile_url.split('@')[-1]

        # Check for cached profile info first if enabled
        raw_profile_info = None
        cached_profile_info = None
        should_update_cache = True  # Default to updating cache
        if use_profile_cache:
            cached_data = await db.get_profile(profile_url, refresh_profile_data)
            if cached_data and 'raw_profile_info' in cached_data:
                logger.debug(f"raw profile info cache hit. Url: {profile_url}")
                raw_profile_info = cached_data['raw_profile_info']
                cached_profile_info = cached_data.copy()
                cached_profile_info.pop('raw_profile_info', None)
                should_update_cache = False
                    
        # If no cached profile info, fetch it
        if raw_profile_info is None or ('Ошибка' in json.dumps(cached_profile_info, ensure_ascii=False) and refetch_profile_with_errors):
            logger.debug(f"Fetching raw profile info. Url: {profile_url}")
            async with aiohttp.ClientSession() as session:
                # choose lookup by channel-ID vs. by username
                if "/channel/" in profile_url:
                    # extract the ID after "/channel/"
                    channel_id = profile_url.split("/channel/")[1].split("?")[0].rstrip("/")
                    request_params = {"id": channel_id}
                else:
                    request_params = {"forUsername": profile_username}

                async with session.get(
                    "https://yt-api.p.rapidapi.com/channel/about",
                    headers={
                        "x-rapidapi-host": "yt-api.p.rapidapi.com",
                        "x-rapidapi-key": os.getenv("RAPIDAPI_API_KEY")
                    },
                    params=request_params
                ) as response:
                    response.raise_for_status()
                    raw_profile_info = await response.json()
            should_update_cache = True
            
        meta_data = raw_profile_info

        # Extract profile name
        try:
            if "title" in meta_data:
                if isinstance(meta_data["title"], str):
                    profile_name_val = meta_data["title"]
                else:
                    profile_name_val = ""
            else:
                profile_name_val = ""
            profile_info['profile_name'] = profile_name_val
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube profile_name for {profile_url}", e)
            profile_info['profile_name'] = f"Ошибка {error_info}"

        # Extract profile description
        try:
            if "description" in meta_data:
                if isinstance(meta_data["description"], str):
                    profile_description_val = meta_data["description"]
                else:
                    profile_description_val = ""
            else:
                profile_description_val = ""
            profile_info['profile_description'] = profile_description_val
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube profile_description for {profile_url}", e)
            profile_info['profile_description'] = f"Ошибка {error_info}"

        # Extract profile subscribers count
        try:
            if "subscriberCount" in meta_data:
                try:
                    profile_subscribers_count_val = int(meta_data["subscriberCount"])
                except Exception as e:
                    profile_subscribers_count_val = meta_data["subscriberCount"]
            else:
                profile_subscribers_count_val = 0
            profile_info['profile_subscribers_count'] = profile_subscribers_count_val
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube profile_subscribers_count for {profile_url}", e)
            profile_info['profile_subscribers_count'] = f"Ошибка {error_info}"

        # Extract profile links
        profile_info['profile_links'] = []
        try:
            # Links associated with the channel
            if "links" in meta_data:
                if isinstance(meta_data["links"], list):
                    links_list = meta_data["links"]
                else:
                    links_list = None
            else:
                links_list = None
            
            if links_list:
                parsed_links = []
                for link_item in links_list:
                    # pick only title and link URL
                    title = link_item["title"] if "title" in link_item else ""
                    url = link_item["link"]  if "link"  in link_item else ""
                    parsed_links.append({"title": title, "url": url})
                profile_info['profile_links'] = parsed_links
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube profile_links for {profile_url}", e)
            profile_info['profile_links'].append(f"Ошибка {error_info}")
    
    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error getting YouTube profile info for {profile_url}", e)
        post_info['debug_info']['add_youtube_profile_info_error_info'] = error_info
        post_info['debug_info']['add_youtube_profile_info_error_message'] = str(e)

    # Cache the profile info with the raw profile info if enabled
    if (update_profile_cache and should_update_cache) or force_update_profile_cache:
        await db.save_profile(profile_url, {'raw_profile_info': raw_profile_info, **profile_info})

    # Add final profile info without raw_profile_info to the post_info
    post_info['profile_info'] = profile_info

    return post_info

async def get_youtube_video_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Process a YouTube video."""

    # Extract parameters from task
    add_info_parameters = task.get("add_info_parameters", {})
    use_profile_cache = add_info_parameters.get("use_profile_cache", True)
    update_profile_cache = add_info_parameters.get("update_profile_cache", True)
    use_post_cache = add_info_parameters.get("use_post_cache", True)
    force_update_profile_cache = add_info_parameters.get("force_update_profile_cache", False)
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
                logger.debug(f"raw video info cache hit. Url: {result['url']}")
                cached_post_info = cached_post['post_info'].copy()
                raw_post_info = cached_post['post_info']['raw_post_info']
                cached_post_info.pop('raw_post_info', None)

        # If no cached post info, fetch it
        if raw_post_info is None or ('Ошибка' in json.dumps(cached_post_info, ensure_ascii=False) and refetch_post_with_errors):
            logger.debug(f"Fetching raw video info. Url: {result['url']}")
            post_info['should_update_cache'] = True
            # Try up to 5 times if the API response has no "title"
            max_retries = 5
            retries = 0
            logger.debug(f"Starting video info fetch with max_retries={max_retries} for URL: {result['url']}")
            
            while retries < max_retries:
                logger.debug(f"Attempt {retries + 1}/{max_retries} for URL: {result['url']}")
                try:
                    raw_post_info = await get_youtube_video_raw_info(result['url'])
                    
                    if raw_post_info:
                        # Check for permanent errors (video removed/unavailable)
                        if "error" in raw_post_info and isinstance(raw_post_info.get("error"), str):
                            error_message = raw_post_info["error"].lower()
                            if "removed" in error_message:
                                logging_utils.log_error(logger, f"Video permanently unavailable for {result['url']}: {raw_post_info['error']}")
                                post_info['processed'] = True
                                post_info['valid'] = False
                                return post_info, raw_post_info
                        
                        if "title" in raw_post_info and raw_post_info["title"]:
                            logger.debug(f"Success on attempt {retries + 1}/{max_retries}: Found title '{raw_post_info['title']}' for URL: {result['url']}")
                            break
                        else:
                            retries += 1
                            title_status = "missing" if "title" not in raw_post_info else f"empty/null (value: {raw_post_info.get('title')})"
                            logger.warning(f"Attempt {retries}/{max_retries} for {result['url']}: title is {title_status}")
                            
                            if retries < max_retries:
                                wait_time = random.uniform(1, 3)
                                logger.debug(f"Waiting {wait_time:.1f} seconds before retry...")
                                await asyncio.sleep(wait_time)
                    else:
                        retries += 1
                        logger.warning(f"Attempt {retries}/{max_retries} for {result['url']}: received null/empty response")
                        
                        if retries < max_retries:
                            wait_time = random.uniform(1, 3)
                            logger.debug(f"Waiting {wait_time:.1f} seconds before retry...")
                            await asyncio.sleep(wait_time)
                            
                except Exception as e:
                    retries += 1
                    logging_utils.log_error(logger, f"Attempt {retries}/{max_retries} for {result['url']} failed with exception: {e}", e)
                    
                    if retries < max_retries:
                        wait_time = random.uniform(1, 3)
                        logger.debug(f"Waiting {wait_time:.1f} seconds before retry...")
                        await asyncio.sleep(wait_time)
                    
            if not raw_post_info or "title" not in raw_post_info:
                logging_utils.log_error(logger, f"Failed to get valid video info after {max_retries} attempts for {result['url']}")
                if raw_post_info:
                    logging_utils.log_error(logger, f"Final response keys: {list(raw_post_info.keys()) if isinstance(raw_post_info, dict) else 'Not a dict'}")
                    logging_utils.log_error(logger, f"Final response preview: {str(raw_post_info)[:500]}...")
                post_info['processed'] = True
                post_info['valid'] = False
                return post_info, raw_post_info
        
        # Title
        try:
            if "title" in raw_post_info:
                if isinstance(raw_post_info["title"], str):
                    title = raw_post_info["title"]
                    logger.debug(f"Successfully extracted title: '{title}' for URL: {result['url']}")
                else:
                    title = ""
                    logger.warning(f"Title field is not a string (type: {type(raw_post_info['title'])}): {raw_post_info['title']} for URL: {result['url']}")
            else:
                title = ""
                logger.warning(f"No title field found in API response for URL: {result['url']}")
            post_info['title'] = title
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube video title for {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['title'] = f"Ошибка {error_info}"
        
        # Publication date
        try:
            published_date = raw_post_info["publishDate"]
            # Convert to YYYY-MM-DD format if needed
            if "T" in published_date:
                date_obj = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                post_info['publication_date'] = date_obj.strftime('%Y-%m-%d')
            else:
                post_info['publication_date'] = published_date
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube video publication date", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"
        
        # Description
        try:
            if "description" in raw_post_info:
                if isinstance(raw_post_info["description"], str):
                    description = raw_post_info["description"]
                else:
                    description = ""
            else:
                description = ""
            post_info['text'] = description
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube video description", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"
        
        # Views count
        try:
            try:
                post_info['views_count'] = int(raw_post_info["viewCount"])
            except Exception:
                post_info['views_count'] = raw_post_info["viewCount"]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube video views count", e)
            result['debug_info']['errors'].append(error_info)
            post_info['views_count'] = f"Ошибка {error_info}"
        
        # Likes count
        try:
            if "likeCount" in raw_post_info:
                raw_likes = raw_post_info["likeCount"]
            else:
                raw_likes = None
            if raw_likes is None:
                post_info['likes_count'] = "Скрыто"
            else:
                post_info['likes_count'] = int(raw_likes)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube video likes count", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"
        
        # Comments count
        try:
            comments_count = raw_post_info.get("commentCount", 0)
            if comments_count:
                post_info['comments_count'] = int(comments_count)
            else:
                post_info['comments_count'] = 0
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube video comments count", e)
            result['debug_info']['errors'].append(error_info)
            post_info['comments_count'] = f"Ошибка {error_info}"
            
        # Age restriction status
        try:
            if "isFamilySafe" in raw_post_info:
                post_info['age_restricted'] = not raw_post_info["isFamilySafe"]
            else:
                post_info['age_restricted'] = False
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube video age restriction status", e)
            result['debug_info']['errors'].append(error_info)
            post_info['age_restricted'] = f"Ошибка {error_info}"

        # Profile URL
        post_info['profile_url'] = ''
        try:
            if raw_post_info.get("channelHandle", None) is None:
                post_info['profile_url'] = f"https://www.youtube.com/channel/{raw_post_info['channelId']}"
            else:
                try:
                    handle = urllib.parse.unquote(raw_post_info["channelHandle"])
                except Exception:
                    handle = raw_post_info["channelHandle"]
                
                post_info['profile_url'] = f"https://www.youtube.com/{handle}"
        except Exception as e:
            error_info = logging_utils.log_error(
                logger,
                f"Error extracting YouTube video profile URL for {result['url']}",
                e
            )
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"
        
        # mark if this profile is excluded; if so, skip fetching further profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_youtube_video_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info

async def get_youtube_shorts_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Process a YouTube shorts video."""
    return await get_youtube_video_info(result, task)

async def get_youtube_post_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Process a YouTube post."""
    
    # Extract parameters from task
    add_info_parameters = task.get("add_info_parameters", {})
    use_profile_cache = add_info_parameters.get("use_profile_cache", True)
    update_profile_cache = add_info_parameters.get("update_profile_cache", True)
    use_post_cache = add_info_parameters.get("use_post_cache", True)
    force_update_profile_cache = add_info_parameters.get("force_update_profile_cache", False)
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
                logger.debug(f"raw post info cache hit. Url: {result['url']}")
                cached_post_info = cached_post['post_info'].copy()
                raw_post_info = cached_post['post_info']['raw_post_info']
                cached_post_info.pop('raw_post_info', None)

        # If no cached post info, fetch it
        if raw_post_info is None or ('Ошибка' in json.dumps(cached_post_info, ensure_ascii=False) and refetch_post_with_errors):
            # 1) extract post ID
            post_id_match = re.search(r'/post/([^?]+)', result['url'])
            if not post_id_match:
                raise ValueError(f"Invalid YouTube Result url: {result['url']}")
            post_id = post_id_match.group(1)

            # 2) fetch post info + comments
            logger.debug(f"Fetching raw post info. Url: {result['url']}")
            async with aiohttp.ClientSession() as session:
                # post/info
                async with session.get(
                    "https://yt-api.p.rapidapi.com/post/info",
                    headers={
                        "x-rapidapi-host": "yt-api.p.rapidapi.com",
                        "x-rapidapi-key": os.getenv("RAPIDAPI_API_KEY")
                    },
                    params={"id": post_id}
                ) as resp_info:
                    resp_info.raise_for_status()
                    post_api_data = await resp_info.json()

                # post/comments
                async with session.get(
                    "https://yt-api.p.rapidapi.com/post/comments",
                    headers={
                        "x-rapidapi-host": "yt-api.p.rapidapi.com",
                        "x-rapidapi-key": os.getenv("RAPIDAPI_API_KEY")
                    },
                    params={"id": post_id}
                ) as resp_comments:
                    resp_comments.raise_for_status()
                    comments_api_data = await resp_comments.json()

            raw_post_info = {
                'post_api_data': post_api_data,
                'comments_api_data': comments_api_data
            }
            post_info['should_update_cache'] = True

        # Extract data from raw_post_info
        post_api_data = raw_post_info.get('post_api_data', {})
        comments_api_data = raw_post_info.get('comments_api_data', {})

        # 3) map fields from post_api_data
        try:
            if "contentText" in post_api_data:
                if isinstance(post_api_data["contentText"], str):
                    post_info['text'] = post_api_data["contentText"]
                else:
                    post_info['text'] = ""
            else:
                post_info['text'] = ""
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube post text", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"

        try:
            post_info['publication_date'] = f"! {post_api_data['publishedTimeText']} (относительно {datetime.now(timezone.utc).strftime('%d-%m-%Y')})"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube post publication date", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"

        try:
            if "voteCountText" in post_api_data:
                parsed_likes_count = utils.parse_number(post_api_data["voteCountText"])
                if not isinstance(parsed_likes_count, str):
                    post_info['likes_count'] = parsed_likes_count
            else:
                post_info['likes_count'] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube post likes count", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"

        # 5) construct author's channel URL
        post_info['profile_url'] = ''
        try:
            post_info['profile_url'] = (
                f"https://www.youtube.com/channel/{post_api_data['authorChannelId']}"
            )
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting YouTube post author channel URL", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_youtube_post_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info