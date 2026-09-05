"""
Twitch processor module for handling Twitch videos and streams.
"""
import sys
import os
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import dotenv
import aiohttp
import json
import asyncio
import copy

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.storage import db
from src.utils import logging_utils
from src.utils import utils

# Setup logger
logger = logging_utils.setup_logger('twitch.py')

# Load environment variables
dotenv.load_dotenv()


async def fetch_scrapeninja_html(url: str) -> Optional[Dict[str, Any]]:
    """Fetch full response using ScrapeNinja API with JS rendering"""
    headers = {
        'X-RapidAPI-Key': os.getenv('RAPIDAPI_API_KEY'),
        'X-RapidAPI-Host': 'scrapeninja.p.rapidapi.com',
        'content-type': 'application/json'
    }
    data = {
        "url": url,
        "method": "GET",
        "retryNum": 1,
        "v2": True,
        "geo": "us",
        "js": True,
        "blockImages": False,
        "blockMedia": False,
        "steps": [],
        "postWaitTime": 10
    }
    
    async with aiohttp.ClientSession() as session:
        retry_count = 0
        max_retries = 10
        base_wait = 1
        
        while retry_count <= max_retries:
            async with session.post(
                'https://scrapeninja.p.rapidapi.com/scrape-js',
                headers=headers,
                json=data
            ) as response:
                status = response.status
                json_response = await response.json()
                logger.debug(f"json response: {json_response}")

                retry_reason = ''
                
                # Check for empty response
                if not json_response or 'body' not in json_response or not json_response['body'].strip():
                    retry_reason = 'empty response'
                elif status == 200:
                    html_content = json_response['body']
                    if 'core-error__message-container' in html_content and "that content is unavailable" not in html_content:
                        retry_reason = 'error container'
                elif status == 429:
                    retry_reason = '429 status code'
                else:
                    response.raise_for_status()

                if retry_reason and retry_count < max_retries:
                    wait_time = base_wait + retry_count
                    logging_utils.log_warning(logger, f"Retrying in {wait_time}s for {url} (attempt {retry_count + 1}/{max_retries}). Retry reason: {retry_reason}")
                    await asyncio.sleep(wait_time)
                    retry_count += 1
                    continue
                
                if 'body' in json_response:
                    return json_response
                else:
                    logging_utils.log_error(logger, f"Failed to get HTML after {max_retries} retries")
                    return None
        
        response.raise_for_status()
        return None


async def add_profile_info(post_info: Dict[str, Any], task: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Parse Twitch profile information from a content info object and add it to the object.
    
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
    
    # Initialize profile_info with default values
    profile_info = {}

    try:
        # Check for cached profile info first if enabled
        raw_profile_info = None
        cached_profile_info = None
        should_update_cache = True  # Default to updating cache
        
        if use_profile_cache:
            cached_profile_info = await db.get_profile(post_info['profile_url'], refresh_profile_data)
            if cached_profile_info and 'raw_profile_info' in cached_profile_info:
                logger.debug(f"Raw profile info cache hit. Url: {post_info['profile_url']}")
                raw_profile_info = cached_profile_info.pop('raw_profile_info')
                should_update_cache = False

        # If no cached profile response, fetch it
        if raw_profile_info is None or ('Ошибка' in json.dumps(cached_profile_info, ensure_ascii=False) and refetch_profile_with_errors):
            logger.debug(f"Fetching raw profile info. Url: {post_info['profile_url']}")
            raw_profile_info = await fetch_scrapeninja_html(post_info['profile_url'] + "/about")
            should_update_cache = True

        if not raw_profile_info or 'body' not in raw_profile_info:
            profile_info["error"] = "Failed to fetch profile HTML"
            post_info['profile_info'] = profile_info
            return post_info

        profile_soup = BeautifulSoup(raw_profile_info['body'], 'html.parser')

        # Extract profile name
        try:
            # Get profile name from the last part of the URL
            profile_info["profile_name"] = post_info['profile_url'].rstrip('/').split('/')[-1]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Twitch profile name. Url: {post_info['profile_url']}", e)
            profile_info["profile_name"] = f"Ошибка {error_info}"

        # Extract profile description
        try:
            profile_info["profile_description"] = ""
            # Look for description in div.about-section__panel--content -> p with dir="auto"
            about_content_div = profile_soup.find('div', class_='about-section__panel--content')
            if about_content_div and hasattr(about_content_div, 'find'):
                desc_p = about_content_div.find('p', attrs={'dir': 'auto'})
                if desc_p and hasattr(desc_p, 'get_text'):
                    profile_info["profile_description"] = desc_p.get_text(strip=True)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Twitch profile description. Url: {post_info['profile_url']}", e)
            profile_info["profile_description"] = f"Ошибка {error_info}"

        # Extract followers count
        try:
            profile_info["profile_subscribers_count"] = 0
            about_content_div = profile_soup.find('div', class_='about-section__panel--content')
            if about_content_div:
                spans = about_content_div.find_all('span')
                for span in spans:
                    text = span.get_text(strip=True)
                    if 'followers' in text:
                        followers_count = text.replace('followers', '').strip()
                        parsed_followers_count = utils.parse_number(followers_count)
                        if not isinstance(parsed_followers_count, str):
                            profile_info["profile_subscribers_count"] = parsed_followers_count
                        break
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Twitch profile followers count. Url: {post_info['profile_url']}", e)
            profile_info["profile_subscribers_count"] = f"Ошибка {error_info}"

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error parsing Twitch profile. Profile url: {post_info['profile_url']}", e)
        post_info['debug_info']['add_profile_info_error_info'] = error_info
        post_info['debug_info']['add_profile_info_error_message'] = str(e)

    # Cache the profile info with the raw profile response if enabled
    if (update_profile_cache and should_update_cache) or force_update_profile_cache:
        await db.save_profile(post_info['profile_url'], {'raw_profile_response': raw_profile_info, **profile_info})

    # Add final profile info without raw_profile_response to the post_info
    post_info['profile_info'] = profile_info
    
    return post_info


async def get_twitch_clip_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process a Twitch clip asynchronously."""
    return await get_twitch_stream_info(result, task)


async def get_twitch_stream_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process a Twitch stream asynchronously."""
    
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
            if cached_post and 'raw_post_info' in cached_post.get('post_info', {}):
                logger.debug(f"Raw post info cache hit. Url: {result['url']}")
                raw_post_info = cached_post['post_info'].pop('raw_post_info')

        if raw_post_info is None or ('Ошибка' in json.dumps(cached_post_info, ensure_ascii=False) and refetch_post_with_errors):
            logger.debug(f"Fetching raw post info. Url: {result['url']}")
            raw_post_info = await fetch_scrapeninja_html(result['url'])
            post_info['should_update_cache'] = True
            
        stream_soup = BeautifulSoup(raw_post_info['body'], 'html.parser')

        # Check for error page
        error_elem = stream_soup.find('p', attrs={"data-a-target": "core-error-message"})
        if error_elem:
            logger.debug(f"Invalid post detected. Result url: {result['url']}")
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info

        # Extract title
        try:
            title_elem = stream_soup.find('p', attrs={"data-a-target": "stream-title"})
            if not title_elem:
                title_elem = stream_soup.find('h2', attrs={"data-a-target": "stream-title"})
            post_info['title'] = title_elem.get_text(strip=True)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Twitch stream title. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['title'] = f"Ошибка {error_info}"

        # Extract profile URL
        try:
            follow_button = stream_soup.find('button', attrs={"data-a-target": "follow-button"})
            aria_label = follow_button.get('aria-label', '').lower()
            username = aria_label.split(' ')[-1]
            post_info['profile_url'] = f"https://twitch.tv/{username}"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Twitch stream profile url. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Extract publication date
        try:
            timestamp_bar = stream_soup.find('hr', class_='timestamp-metadata__bar')
            date_elem = timestamp_bar.find_next_sibling('p')
            publication_date = date_elem.get_text(strip=True)
            post_info['publication_date'] = f"! {publication_date} (относительно {datetime.now(timezone.utc).strftime('%Y-%m-%d')})"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Twitch publication date. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"

        # Extract views count
        try:
            views_p = stream_soup.find('p', string=lambda text: text and 'views' in text)
            if views_p:
                text = views_p.get_text(strip=True)
                count_str = text.replace('views', '').replace(',', '').strip()
                post_info['views_count'] = int(count_str)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Twitch viewers count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['views_count'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_twitch_stream_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info