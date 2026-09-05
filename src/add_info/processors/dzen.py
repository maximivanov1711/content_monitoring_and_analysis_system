"""
Dzen processor module for handling Dzen articles, news, and videos.
"""
import sys
import os
import json
from typing import Dict, Any, Tuple
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib import parse
import asyncio

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.storage import db
from src.add_info import apify_parser
from src.utils import logging_utils
from src.utils import utils

# Setup logger
logger = logging_utils.setup_logger('dzen.py')


async def get_dzen_html_with_retry(url: str, content_type: str, max_retries: int = 3, wait_time: int = 7) -> str | None:
    """
    Get Dzen HTML content with retry logic for both posts and profiles.
    
    Args:
        url: The URL to fetch
        content_type: Either "profile" or "post"
        max_retries: Maximum number of retry attempts
        wait_time: Wait time for each request
        
    Returns:
        Raw HTML response data or None if failed
    """
    
    delay = 1

    for attempt in range(max_retries):

        if attempt > 0:
            await asyncio.sleep(delay)
            delay += 1

        try:
            logger.debug(f"Fetching raw HTML (attempt {attempt+1}/{max_retries}). Url: {url}, type: {content_type}")
            raw_html_data = await apify_parser.get_raw_html(url, wait_until="domcontentloaded")
            
            if not raw_html_data:
                logger.warning(f"No HTML data received, retrying (attempt {attempt+1}/{max_retries})")
                continue
            
            logger.debug(f"Successfully fetched {content_type} HTML. Url: {url}")
            return raw_html_data
            
        except Exception as e:
            logging_utils.log_error(logger, f"Error fetching {content_type} HTML (attempt {attempt+1}/{max_retries}). Url: {url}", e)
            continue

    logging_utils.log_error(logger, f"Error fetching {content_type} HTML after {max_retries} attempts. Url: {url}")
    return None


async def add_profile_info(post_info: Dict[str, Any], task: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Parse Dzen profile information from a content info object and add it to the object.
    
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
            raw_profile_info = await get_dzen_html_with_retry(post_info['profile_url'], "profile")
            if raw_profile_info is None:
                profile_info["error"] = "Failed to fetch profile HTML"
                post_info['profile_info'] = profile_info
                return post_info
            should_update_cache = True

        raw_profile_html = raw_profile_info
        profile_soup = BeautifulSoup(raw_profile_html, 'html.parser')

        # Extract profile name
        try:
            og_title_meta = profile_soup.find('meta', attrs={'property': 'og:title'})
            if og_title_meta and 'content' in og_title_meta.attrs:
                profile_info['profile_name'] = og_title_meta['content'][:-len(' | Дзен')].strip()
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen profile name. Url: {post_info['profile_url']}", e)
            profile_info['profile_name'] = f"Ошибка {error_info}"

        # Extract profile description
        try:
            description_meta = profile_soup.find('meta', attrs={'name': 'og:description'})
            description_content = description_meta['content']
            # Remove the initial part of the description if it matches the pattern
            description_content = description_content.split("⭐: ", 1)[-1]
            profile_info['profile_description'] = description_content.strip()
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen profile description. Url: {post_info['profile_url']}", e)
            profile_info['profile_description'] = f"Ошибка {error_info}"
        
        # Extract profile subscribers count
        try:
            profile_info['profile_subscribers_count'] = 0
            counter_elem = profile_soup.find('div', class_=lambda c: c and 'channel-counter__counter-' in c)
            value_div = counter_elem.find('div', class_=lambda c: c and 'channel-counter__value-' in c)
            parsed_subscribers_count = utils.parse_number(value_div.get_text(strip=True))
            if not isinstance(parsed_subscribers_count, str):
                profile_info['profile_subscribers_count'] = parsed_subscribers_count
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen profile subscribers count. Url: {post_info['profile_url']}", e)
            profile_info['profile_subscribers_count'] = f"Ошибка {error_info}"

        # Extract profile ssrData from profile html
        profile_ssrData = None
        try:
            # Find all scripts in the profile html
            ssr_scripts = profile_soup.find_all('script')
            
            # Try to find the ssrData in the scripts
            for i, script in enumerate(ssr_scripts):
                script_text = script.string
                if not script_text or '"ssrData":' not in script_text:
                    continue
                
                try:
                    # Attempt to find the JSON object containing "ssrData"
                    json_start_index = -1
                    # Find the beginning of the potential JSON object around "ssrData"
                    ssr_data_key_index = script_text.find('"ssrData":')
                    # Search backwards for the opening brace of the object containing ssrData
                    search_start = ssr_data_key_index
                    potential_starts = [i for i, char in enumerate(script_text[:search_start]) if char == '{']
                    if not potential_starts:
                        continue
                        
                    # Try parsing from the closest preceding '{'
                    json_start_index = potential_starts[-1]

                    # Find the matching closing brace
                    brace_level = 0
                    json_end_index = -1
                    for j, char in enumerate(script_text[json_start_index:]):
                        if char == '{':
                            brace_level += 1
                        elif char == '}':
                            brace_level -= 1
                            if brace_level == 0:
                                json_end_index = json_start_index + j
                                break
                    
                    if json_end_index == -1:
                        continue

                    json_str = script_text[json_start_index : json_end_index + 1]
                    
                    # Parse the extracted JSON string
                    ssr_data = json.loads(json_str)
                    
                    # Check for the required nested structure
                    if 'ssrData' in ssr_data and 'exportResponse' in ssr_data['ssrData'] and 'channel' in ssr_data['ssrData']['exportResponse']:
                        profile_ssrData = ssr_data['ssrData']['exportResponse']['channel']
                        break # Found the data, exit the loop
                        
                # If the JSON is not valid, continue to the next script
                except json.JSONDecodeError:
                    pass   
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting profile ssrData. Url: {post_info['profile_url']}", e)

        # Extract profile links from profile ssrData
        profile_info['profile_links'] = []
        try:
            if isinstance(profile_ssrData, dict) and 'source' in profile_ssrData:
                raw_info_source = profile_ssrData['source']
                
                if isinstance(raw_info_source, dict):
                    # Add main external link first
                    main_link = raw_info_source.get('main_external_link')
                    if main_link and isinstance(main_link, str):
                        profile_info['profile_links'].append({
                            "title": "Основная ссылка",
                            "url": main_link
                        })

                    # Add other social links
                    social_links = raw_info_source.get('social_links')
                    if isinstance(social_links, list):
                        for link_info in social_links:
                            if isinstance(link_info, dict):
                                name = link_info.get('name')
                                link = link_info.get('link')
                                if name and link and isinstance(name, str) and isinstance(link, str):
                                    # Avoid adding the main link again if it's also in social_links
                                    if not any(existing_link['url'] == link for existing_link in profile_info['profile_links']):
                                        profile_info['profile_links'].append({
                                            "title": name,
                                            "url": link
                                        })
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting social links. Url: {post_info['profile_url']}", e)
            profile_info['profile_links'].append(f"Ошибка {error_info}")
            
    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error parsing Dzen profile. Profile url: {post_info['profile_url']}", e)
        post_info['debug_info']['add_profile_info_error_info'] = error_info
        post_info['debug_info']['add_profile_info_error_message'] = str(e)

    # Cache the profile info with the raw profile HTML if enabled
    if (update_profile_cache and should_update_cache) or force_update_profile_cache:
        await db.save_profile(post_info['profile_url'], {'raw_profile_info': raw_profile_info, **profile_info})
    
    # Add final profile info without raw_profile_info to the post_info
    post_info['profile_info'] = profile_info

    return post_info

async def get_dzen_article_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process a Dzen article asynchronously."""

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
            raw_post_info = await get_dzen_html_with_retry(result['url'], "post")
            post_info['should_update_cache'] = True

        raw_post_html = raw_post_info
        post_soup = BeautifulSoup(raw_post_html, 'html.parser')

        # If the post is not valid, return the post_info with processed = True and valid = False
        if post_soup.find('body', class_=lambda c: c and 'page_error' in c):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info
        
        # Extract article text
        try:
            article_text_elem = post_soup.find('div', attrs={'itemprop': 'articleBody'})
            post_info['text'] = article_text_elem.get_text(separator='\n', strip=True)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen article text. Article url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"

        # Extract links from article content
        post_info['links'] = []
        try:
            article_text_elem = post_soup.find('div', attrs={'itemprop': 'articleBody'})
            link_elements = article_text_elem.find_all('a', class_=lambda c: c and 'content--article-link__articleLink' in c)
            for link in link_elements:
                href = link['href']
                # Remove '/away?to=' prefix
                if href.startswith('/away?to='):
                    href = parse.unquote(href[len('/away?to='):])
                post_info['links'].append(href)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen article links. Article url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['links'].append(f"Ошибка {error_info}")
        
        # Extract article title
        try:
            title_elem = post_soup.find('h1', attrs={'itemprop': 'headline'})
            post_info['title'] = title_elem.get_text(strip=True)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen article title. Article url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['title'] = f"Ошибка {error_info}"

        # Extract article publication date
        try:
            date_elem = post_soup.find('div', class_=lambda c: c and 'content--article-info-block__addTimeInfo' in c)
            relative_date_span = date_elem.find('span', class_=lambda c: c and 'content--article-info-block__longFormat' in c)
            publication_date_text = relative_date_span.get_text(strip=True)
            # Convert the relative date to YYYY-MM-DD format
            try:
                # Parse the date text and convert to standard format
                date_obj = datetime.strptime(publication_date_text, "%d %B %Y")
                publication_date = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                # If parsing fails, keep the original text
                publication_date = publication_date_text
            post_info['publication_date'] = f"! {publication_date} (относительно {datetime.now(timezone.utc).strftime('%Y-%m-%d')})"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen article publication date. Article url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"

        # Extract article views count
        try:
            views_meta = post_soup.find('meta', attrs={'itemprop': 'reviewCount'})
            post_info['views_count'] = int(views_meta['content'])
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen views count. Article url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['views_count'] = f"Ошибка {error_info}"

        # Extract article likes count
        try:
            post_info['likes_count'] = 0
            likes_elem = post_soup.find('button', class_=lambda c: c and 'content--button-like__buttonLike' in c)
            likes_text_span = likes_elem.find('span', class_=lambda c: c and 'content--button-like__text' in c)
            if likes_text_span:
                parsed_likes_count = utils.parse_number(likes_text_span.get_text(strip=True))
                if not isinstance(parsed_likes_count, str):
                    post_info['likes_count'] = parsed_likes_count
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen likes count. Article url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"

        # Extract article comments count
        try:
            post_info['comments_count'] = 'Комментарии отключены'
            comments_elem = post_soup.find('span', class_=lambda c: c and 'content--card-block-social-meta-view__cardBlockSocialMetaView' in c)
            if comments_elem:
                button_content = comments_elem.find('span', class_=lambda c: c and 'content--button-footer__content' in c)
                text_span = button_content.find('span', class_=lambda c: c and 'content--button-footer__text' in c)
                if text_span:
                    parsed_comments_count = utils.parse_number(text_span.get_text(strip=True))
                    if not isinstance(parsed_comments_count, str):
                        post_info['comments_count'] = parsed_comments_count
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen comments count. Article url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['comments_count'] = f"Ошибка {error_info}"

        # Extract profile url
        post_info['profile_url'] = ""
        try:
            profile_link_elem = post_soup.find('a', class_=lambda c: c and 'content--publisher-block-inline__channelNameBlock' in c)
            original_url = profile_link_elem['href'].split('?')[0]
            if not original_url.startswith('https://'):
                original_url = f"https://dzen.ru{original_url}"
            post_info['profile_url'] = original_url
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen article profile url. Article url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_dzen_article_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info

async def get_dzen_post_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process a Dzen post asynchronously."""

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
            raw_post_info = await get_dzen_html_with_retry(result['url'], "post")
            post_info['should_update_cache'] = True

        raw_post_html = raw_post_info
        post_soup = BeautifulSoup(raw_post_html, 'html.parser')
        
        # If the post is not valid, return the post_info with processed = True and valid = False
        if post_soup.find('body', class_=lambda c: c and 'page_error' in c):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info
        
        # Extract post text
        try:
            post_text_elem = post_soup.find('div', class_=lambda c: c and 'brief-viewer--rich-text__richText' in c)
            post_info['text'] = post_text_elem.get_text(separator='\n', strip=True)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen post text. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"

        # Extract links from post content
        post_info['links'] = []
        try:
            post_text_elem = post_soup.find('div', class_=lambda c: c and 'brief-viewer--rich-text__richText' in c)
            link_elements = post_text_elem.find_all('a', class_=lambda c: c and 'brief-viewer--rich-text__link' in c)
            for link in link_elements:
                href = link['href']
                # Remove '/away?to=' prefix
                if href.startswith('/away?to='):
                    href = parse.unquote(href[len('/away?to='):])
                post_info['links'].append(href)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen post links. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['links'].append(f"Ошибка {error_info}")

        # Extract post publication date
        try:
            date_elem = post_soup.find('div', class_=lambda c: c and 'brief-viewer--article-stats-view__item' in c, attrs={'itemprop': 'datePublished'})
            iso_date = date_elem['content']
            if 'T' in iso_date:
                date_part = iso_date.split('T')[0]
                post_info['publication_date'] = date_part
            else:
                post_info['publication_date'] = iso_date
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen post publication date. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"

        # Extract post likes count
        try:
            post_info['likes_count'] = 0
            likes_text_elem = post_soup.find('span', class_=lambda c: c and 'brief-viewer--button-like__text' in c)
            if likes_text_elem:
                parsed_likes_count = utils.parse_number(likes_text_elem.get_text(strip=True))
                if not isinstance(parsed_likes_count, str):
                    post_info['likes_count'] = parsed_likes_count
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen post likes count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"

        # Extract post comments count
        try:
            post_info['comments_count'] = 0
            comments_text_elem = post_soup.find('span', class_=lambda c: c and 'brief-viewer--button-footer__text' in c)
            if comments_text_elem:
                parsed_comments_count = utils.parse_number(comments_text_elem.get_text(strip=True))
                if not isinstance(parsed_comments_count, str):
                    post_info['comments_count'] = parsed_comments_count
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen post comments count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['comments_count'] = f"Ошибка {error_info}"

        # Extract profile url
        post_info['profile_url'] = ""
        try:
            profile_link_elem = post_soup.find('a', class_=lambda c: c and 'brief-viewer--channel-info__link' in c)
            original_url = profile_link_elem['href'].split('?')[0]
            if not original_url.startswith('https://'):
                original_url = f"https://dzen.ru{original_url}"
            post_info['profile_url'] = original_url
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen post profile url. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True
        
        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_dzen_post_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info

async def get_dzen_news_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process a Dzen news item asynchronously."""

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
            raw_post_info = await get_dzen_html_with_retry(result['url'], "post")
            post_info['should_update_cache'] = True

        raw_post_html = raw_post_info
        news_soup = BeautifulSoup(raw_post_html, 'html.parser')
        
        # If the post is not valid, return the post_info with processed = True and valid = False
        if news_soup.find('div', class_=lambda c: c and 'news-site--empty-state__imgWrapper' in c):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info

        # Extract news title
        try:
            post_info['title'] = ""
            title_elem = news_soup.find('h1', class_=lambda c: c and 'news-site--StoryHead' in c)
            if title_elem:
                post_info['title'] = title_elem.get_text(strip=True)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen news title. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['title'] = f"Ошибка {error_info}"
        
        # Extract news text
        try:
            post_info['text'] = ""
            story_digest = news_soup.find(attrs={'data-testid': 'story-digest'})
            if story_digest:
                post_info['text'] = story_digest.get_text(separator='', strip=True)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen news text. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"
        
        # Extract news publication date
        try:
            post_info['publication_date'] = "Отсутствует"
            date_elem = news_soup.find('div', class_=lambda c: c and 'news-story-block__time' in c)
            if date_elem:
                post_info['publication_date'] = f"! {date_elem.get_text(strip=True)} (относительно {datetime.now(timezone.utc).strftime('%Y-%m-%d')})"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen news publication date. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"

        post_info['processed'] = True
        
        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_dzen_news_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info

async def get_dzen_short_video_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process a Dzen short video asynchronously."""

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
            raw_post_info = await get_dzen_html_with_retry(result['url'], "post")
            post_info['should_update_cache'] = True

        raw_post_html = raw_post_info
        video_soup = BeautifulSoup(raw_post_html, 'html.parser')
        
        # If the post is not valid, return the post_info with processed = True and valid = False
        if video_soup.find('div', class_=lambda c: c and 'shorts--error-page' in c):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info
        
        # Extract video text
        try:
            og_title_meta = video_soup.find('meta', attrs={'property': 'og:title'})
            if og_title_meta and 'content' in og_title_meta.attrs:
                full_content = og_title_meta['content']
                parts = full_content.split("|")
                if len(parts) >= 3:
                    post_info['title'] = "|".join(parts[1:-1]).strip()
                else:
                    post_info['title'] = full_content
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video description. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['title'] = f"Ошибка {error_info}"

        # Extract profile url
        post_info['profile_url'] = ""
        try:
            profile_link_elem = video_soup.find('a', class_=lambda c: c and 'shorts--channel-info__link' in c)
            if profile_link_elem and 'href' in profile_link_elem.attrs:
                post_info['profile_url'] = profile_link_elem['href'].split('?')[0]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video profile url. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Extract video likes count
        try:
            post_info['likes_count'] = 0
            likes_count_elem = video_soup.find('div', attrs={'data-testid': 'short-likes-counter'})
            if likes_count_elem:
                parsed_likes_count = utils.parse_number(likes_count_elem.get_text(strip=True))
                if not isinstance(parsed_likes_count, str):
                    post_info['likes_count'] = parsed_likes_count
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video likes count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"

        # Extract video comments count
        try:
            post_info['comments_count'] = 0
            comments_button = video_soup.find('button', attrs={'data-testid': 'short-add-comment'})
            if comments_button:
                comments_count_elem = comments_button.find_next_sibling('div', class_=lambda c: c and 'shorts--short-social-controls__socialCount' in c)
                if comments_count_elem:
                    parsed_comments_count = utils.parse_number(comments_count_elem.get_text(strip=True))
                    if not isinstance(parsed_comments_count, str):
                        post_info['comments_count'] = parsed_comments_count
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video comments count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['comments_count'] = f"Ошибка {error_info}"

        # Extract video views count
        try:
            post_info['views_count'] = 0
            views_meta = video_soup.find('meta', attrs={'property': 'ya:ovs:views_total'})
            if views_meta and 'content' in views_meta.attrs:
                post_info['views_count'] = int(views_meta['content'])
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video views count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['views_count'] = f"Ошибка {error_info}"

        # Extract video publication date
        try:
            post_info['publication_date'] = "Отсутствует"
            date_meta = video_soup.find('meta', attrs={'property': 'ya:ovs:upload_date'})
            if date_meta and 'content' in date_meta.attrs:
                publication_date_text = date_meta['content']
                try:
                    if 'T' in publication_date_text:
                        date_part = publication_date_text.split('T')[0]
                        post_info['publication_date'] = date_part
                    else:
                        post_info['publication_date'] = publication_date_text
                except ValueError:
                    post_info['publication_date'] = publication_date_text
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video publication date. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True
        
        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_dzen_short_video_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info

async def get_dzen_long_video_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process a Dzen long video asynchronously."""

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
            raw_post_info = await get_dzen_html_with_retry(result['url'], "post")
            post_info['should_update_cache'] = True

        raw_post_html = raw_post_info
        video_soup = BeautifulSoup(raw_post_html, 'html.parser')
        
        # If the post is not valid, return the post_info with processed = True and valid = False
        if video_soup.find('div', class_=lambda c: c and 'error-page-main' in c):
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info
        
        # Check if video is actually a short video
        try:
            og_url_meta = video_soup.find('meta', property='og:url')
            if og_url_meta and 'content' in og_url_meta.attrs and og_url_meta['content'].startswith("https://dzen.ru/shorts/"):
                return await get_dzen_short_video_info(result, task)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error checking if video is a short. Url: {result['url']}", e)

        # Extract JSON-LD video data
        try:
            json_ld_script = video_soup.find('script', id='video-microdata', type='application/ld+json')
            video_data = json.loads(json_ld_script.string) if json_ld_script else {}
        except Exception as e:
            video_data = {}
            logging_utils.log_error(logger, f"Error extracting JSON-LD data. Url: {result['url']}", e)
        
        # Extract video title
        try:
            post_info['title'] = ""
            if 'name' in video_data:
                post_info['title'] = video_data['name']
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video title. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['title'] = f"Ошибка {error_info}"
        
        # Extract video text
        try:
            post_info['text'] = ""
            if 'description' in video_data:
                video_description = video_data['description']
                if "Видео автора «" in video_description and "в Дзене 🎦:" in video_description:
                    pattern_end = video_description.find("в Дзене 🎦:") + len("в Дзене 🎦:")
                    post_info['text'] = video_description[pattern_end:].strip()
                else:
                    post_info['text'] = video_description
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video text. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"
        
        # Extract video publication date
        try:
            post_info['publication_date'] = "Отсутствует"
            if 'uploadDate' in video_data:
                publication_date_text = video_data['uploadDate']
                try:
                    if 'T' in publication_date_text:
                        date_part = publication_date_text.split('T')[0]
                        post_info['publication_date'] = date_part
                    else:
                        post_info['publication_date'] = publication_date_text
                except ValueError:
                    post_info['publication_date'] = publication_date_text
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video publication date. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"

        # Extract video views count
        try:
            post_info['views_count'] = 0
            if 'interactionStatistic' in video_data:
                for stat in video_data['interactionStatistic']:
                    if stat.get('interactionType', {}).get('@type') == 'WatchAction':
                        post_info['views_count'] = int(stat.get('userInteractionCount', 0))
                        break
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video views count. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['views_count'] = f"Ошибка {error_info}"

        # Extract video likes count
        try:
            post_info['likes_count'] = 0
            if 'interactionStatistic' in video_data:
                for stat in video_data['interactionStatistic']:
                    if stat.get('interactionType', {}).get('@type') == 'LikeAction':
                        post_info['likes_count'] = int(stat.get('userInteractionCount', 0))
                        break
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video likes count. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"

        # Extract video comments count
        try:
            post_info['comments_count'] = 0
            if 'interactionStatistic' in video_data:
                for stat in video_data['interactionStatistic']:
                    if stat.get('interactionType', {}).get('@type') == 'CommentAction':
                        post_info['comments_count'] = int(stat.get('userInteractionCount', 0))
                        break
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video comments count. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['comments_count'] = f"Ошибка {error_info}"

        # Extract profile url
        post_info['profile_url'] = ""
        try:
            profile_link_elem = video_soup.find('a', class_=lambda c: c and 'card-channel-link__cardChannelLink' in c)
            post_info['profile_url'] = profile_link_elem['href'].split('?')[0]
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting Dzen video profile url. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True
        
        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_dzen_long_video_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info