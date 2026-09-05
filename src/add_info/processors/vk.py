"""
VK processor module for handling VK posts, articles, videos, and podcasts.
"""
import sys
import copy
from typing import Dict, Any, Tuple
import bs4
import datetime
from urllib import parse
import re
import urlextract
import json
import html
import asyncio

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils
from src.utils import utils
from src.storage import db
from src.add_info import oxylabs_parser


# Setup logger
logger = logging_utils.setup_logger('vk.py')

# Initialize URL extractor
extractor = urlextract.URLExtract()


async def get_vk_html_with_retry(url: str, type: str, max_retries: int = 3, wait_time: int = 10) -> Dict[str, Any] | None:
    """
    Get VK HTML content with retry logic for both posts and profiles.
    
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
            logger.debug(f"Fetching raw HTML (attempt {attempt+1}/{max_retries}). Url: {url}, type: {type}")
            raw_html_data = await oxylabs_parser.get_raw_html(url, wait_time=wait_time)
            raw_html = raw_html_data["results"][0]["content"]
            
            # Check for robot detection error
            if '<svg class="robot-error hidden"' in raw_html:
                logger.warning(f"Robot detection error, retrying (attempt {attempt+1}/{max_retries})")
                continue
            
            # Check for wk_wiki_content only for profile type with club URLs
            if type == "profile" and '?w=club' in url and 'wk_wiki_content' not in raw_html:
                logger.warning(f"wk_wiki_content not found in club profile, retrying (attempt {attempt+1}/{max_retries})")
                continue
            
            # Check for post date element only for post type
            if type == "post":
                post_soup = bs4.BeautifulSoup(raw_html, 'html.parser')
                post_date_elem = post_soup.find('a', attrs={'data-testid': 'post_date_block_preview'})
                if not post_date_elem:
                    logger.warning(f"Post date element not found, retrying (attempt {attempt+1}/{max_retries})")
                    continue
            
            logger.debug(f"Successfully fetched {type} HTML. Url: {url}")
            return raw_html_data
            
        except Exception as e:
            logging_utils.log_error(logger, f"Error fetching {type} HTML (attempt {attempt+1}/{max_retries}). Url: {url}", e)
            continue

    logging_utils.log_error(logger, f"Error fetching {type} HTML after {max_retries} attempts. Url: {url}")
    return None


async def add_profile_info(post_info: Dict[str, Any], task: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Parse VK profile information from a content info object and add it to the object.
    
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
            raw_profile_info = await get_vk_html_with_retry(post_info['profile_url'], "profile")
            should_update_cache = True

        raw_profile_html = raw_profile_info["results"][0]["content"]
        profile_soup = bs4.BeautifulSoup(raw_profile_html, 'html.parser')

        # Determine if it's a group by checking the og:url meta tag
        is_group = False
        og_url_elem = profile_soup.find('meta', property='og:url')
        if og_url_elem:
            og_url_content = og_url_elem.get('content', '')
            # Check for group indicators: 'public', 'club', or presence of group-specific elements
            is_group = 'public' in str(og_url_content) or 'club' in str(og_url_content)

        # Extract profile subscribers count
        try:
            if is_group:
                subscribers_count_elem = None
                if profile_soup.find('div', id='public_followers'):
                    subscribers_elem = profile_soup.find('div', id='public_followers')
                    subscribers_count_elem = subscribers_elem.find('span', class_='header_count')
                elif profile_soup.find('div', id='group_followers'):
                    subscribers_elem = profile_soup.find('div', id='group_followers')
                    subscribers_count_elem = subscribers_elem.find('span', class_='header_count')
                elif profile_soup.find('span', class_='group_friends_count'):
                    subscribers_count_elem = profile_soup.find('span', class_='group_friends_count')
                
                subscribers_text = subscribers_count_elem.text.replace(' ', '').replace(',', '').strip()
                parsed_subscribers_count = utils.parse_number(subscribers_text)
                if not isinstance(parsed_subscribers_count, str):
                    profile_info["profile_subscribers_count"] = parsed_subscribers_count
            else:
                profile_info["profile_subscribers_count"] = 'Неизвестно для личных страниц'
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK profile subscribers count. Url: {post_info['profile_url']}", e)
            profile_info["profile_subscribers_count"] = f"Ошибка {error_info}"

        # Extract profile description
        try:
            profile_info['profile_description'] = ''
            if is_group:
                group_desc_row_wrapper = profile_soup.find('div', class_=lambda c: c and 'wk_wiki_content' in c)

                # Extract status text
                status_desc_row = group_desc_row_wrapper.find('div', class_='group_info_row status')
                if status_desc_row:
                    status_text = status_desc_row.get_text(separator=' ', strip=True)
                    profile_info['profile_description'] = f"Статус:\n{status_text}"

                # Extract description text
                group_desc_row = group_desc_row_wrapper.find('div', class_='group_info_row info')
                if group_desc_row:
                    description_text = group_desc_row.get_text(separator=' ', strip=True)
                    profile_info['profile_description'] += f"\n\nОписание:\n{description_text}"
            else:
                # Extract description text
                desc_div = profile_soup.find('div', class_='ProfileInfo__status')
                if desc_div:
                    description_text = desc_div.get_text(separator=' ', strip=True)
                    profile_info['profile_description'] = description_text
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK profile description. Url: {post_info['profile_url']}", e)
            profile_info["profile_description"] = f"Ошибка {error_info}"

        # Extract profile name
        try:
            profile_name_elem = profile_soup.find('meta', property='og:title')
            if profile_name_elem:
                profile_info["profile_name"] = profile_name_elem['content']
            else:
                profile_name_elem = profile_soup.find('div', class_='group_info_row name')
                profile_info["profile_name"] = profile_name_elem.text.strip()
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK profile name. Url: {post_info['profile_url']}", e)
            profile_info["profile_name"] = f"Ошибка {error_info}"

        # Extract profile links
        profile_info["profile_links"] = []
        try:
            links_div = profile_soup.find('div', id='public_links')
            if links_div:
                link_cells = links_div.find_all('div', class_='line_cell')
                for cell in link_cells:
                    link_title = "Ссылка без названия"
                    
                    title_elem = cell.find('div', class_='group_name')
                    if title_elem and title_elem.find('a'):
                        link_title = title_elem.find('a').text.strip()
                    
                    link_elem = cell.find('a', href=True)
                    link_url = link_elem['href']
                    if link_url.startswith('/away.php?to='):
                        link_url = parse.unquote(link_url.split('to=')[1])
                    
                    profile_info["profile_links"].append({
                        'title': link_title,
                        'url': link_url
                    })
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK profile links. Url: {post_info['profile_url']}", e)
            profile_info["profile_links"].append(f"Ошибка {error_info}")

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error parsing VK profile. Profile url: {post_info['profile_url']}", e)
        post_info['debug_info']['add_profile_info_error_info'] = error_info
        post_info['debug_info']['add_profile_info_error_message'] = str(e)
        
    # Cache the profile info with the raw profile HTML if enabled
    if (update_profile_cache and should_update_cache) or force_update_profile_cache:
        await db.save_profile(post_info['profile_url'], {'raw_profile_info': raw_profile_info, **profile_info})
    
    # Add final profile info without raw_profile_info to the post_info
    post_info['profile_info'] = profile_info

    return post_info

async def get_vk_post_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process a VK post asynchronously."""
    
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
            raw_post_info = await get_vk_html_with_retry(result['url'], "post")
            post_info['should_update_cache'] = True
        
        raw_post_html = raw_post_info["results"][0]["content"]
        post_soup = bs4.BeautifulSoup(raw_post_html, 'html.parser')
        
        # Check for error button which indicates invalid post
        back_button = post_soup.find('button', id='msg_back_button')
        if back_button:
            logger.debug(f"Invalid post detected. Result url: {result['url']}")
            post_info['processed'] = True
            post_info['valid'] = False
            return post_info, raw_post_info

        # Extract post text
        try:
            post_info['text'] = ''
            description_meta_elem = post_soup.find('meta', property='og:description')
            if description_meta_elem:
                post_info['text'] = description_meta_elem['content']
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK post text. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"

        # Extract publication date
        try:
            post_date_elem = post_soup.find('a', attrs={'data-testid': 'post_date_block_preview'})
            relative_date = post_date_elem.text.strip()
            publication_date = f"! {relative_date} (относительно {datetime.datetime.now(datetime.timezone.utc).strftime('%d-%m-%Y')})"
            post_info['publication_date'] = publication_date
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK post date. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"

        # Extract likes count
        try:
            post_info['likes_count'] = 0
            likes_count_elem = post_soup.find('div', class_='ReactionsPreview__count')
            if likes_count_elem:
                parsed_likes_count = utils.parse_number(likes_count_elem.text.strip())
                if not isinstance(parsed_likes_count, str):
                    post_info['likes_count'] = parsed_likes_count
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK post likes count. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"
        
        # Extract links from post text
        post_info['links'] = []
        try:
            link_elems = post_soup.find_all('a', class_=lambda c: c and 'vkitLink__link' in c)
            for link_elem in link_elems:
                link_url = link_elem['href']

                if link_url.startswith('/away.php?to'):
                    # Remove the away.php?to= part and decode the rest
                    link_url = parse.unquote(link_url.split('to=')[1])
                elif link_url.startswith('/'):
                    link_url = f"https://vk.com{link_url}"

                if link_url == result['url']:
                    continue

                post_info['links'].append(link_url)
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK post links. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['links'].append(f"Ошибка {error_info}")

        # Extract video attachments
        try:
            video_attachments = post_soup.find_all('a', class_=lambda c: c and 'vkitInteractiveWrapper__root' in c)
            for attachment in video_attachments:
                if attachment['href'] and attachment['href'].startswith('/video'):
                    # Check if the attachment is a YouTube video
                    youtube_label = attachment.find('span', string='YouTube')
                    if youtube_label:
                        # Find the YouTube iframe
                        youtube_iframe = post_soup.find('iframe', class_='video_yt_player')
                        if youtube_iframe:
                            src = youtube_iframe['src']
                            video_id = src.split('/embed/')[1].split('?')[0]
                            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                            post_info['links'].append(youtube_url)
                    else:
                        post_info['links'].append(f"https://vk.com{attachment['href']}")
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK post video attachments. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['links'].append(f"Ошибка {error_info}")

        # Extract profile url
        post_info['profile_url'] = ""
        try:
            # First try to extract from data-authors attribute
            coauthors_elem = post_soup.find('div', class_='PostHeader--coauthorsWrapper')
            if coauthors_elem and coauthors_elem.get('data-authors'):
                authors_json_str = html.unescape(coauthors_elem['data-authors'])
                authors_data = json.loads(authors_json_str)
                
                # Look for the main author (isAuthor: true) first, then any author
                main_author = None
                for author in authors_data:
                    if author.get('isAuthor', False):
                        main_author = author
                        break
                
                if not main_author and authors_data:
                    main_author = authors_data[0]
                
                if main_author and main_author.get('href'):
                    profile_path = main_author['href'].lstrip('/')
                    author_id = main_author.get('id')
                    if author_id and author_id < 0:
                        # Negative ID means it's a group/community, add club parameter
                        club_id = abs(author_id)
                        post_info['profile_url'] = f"https://vk.com/{profile_path}?w=club{club_id}"
                    else:
                        post_info['profile_url'] = f"https://vk.com/{profile_path}"
            
            # If not found via data-authors, fall back to original method
            if not post_info['profile_url']:
                profile_url_elem = post_soup.find('a', class_=lambda c: c and 'PostHeaderTitle__authorLink' in c)
                profile_path = profile_url_elem['href'].lstrip('/')
                match = re.search(r'/wall(-?\d+)_', result['url'] or "")
                if match and match.group(1).startswith('-'):
                    club_id = match.group(1).lstrip('-')
                    post_info['profile_url'] = f"https://vk.com/{profile_path}?w=club{club_id}"
                else:
                    post_info['profile_url'] = f"https://vk.com/{profile_path}"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK post profile url. Result url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_vk_post_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info

async def get_vk_video_info(result: Dict[str, Any], task: Dict[str, Any] = {}) -> Tuple[Dict[str, Any], str | None]:
    """Process a VK video asynchronously."""
    
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

        # Extract video title
        try:
            post_info['title'] = raw_post_info['title']
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK video title. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['title'] = f"Ошибка {error_info}"

        # Extract video description
        try:
            post_info['text'] = raw_post_info.get('description', '')
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK video description. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['text'] = f"Ошибка {error_info}"

        # Extract publication date (convert timestamp to readable format)
        try:
            timestamp = raw_post_info['date']
            publication_date = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            post_info['publication_date'] = publication_date
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK video date. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['publication_date'] = f"Ошибка {error_info}"

        # Extract likes count
        try:
            if 'likes' not in raw_post_info:
                post_info['likes_count'] = 0
            elif raw_post_info['can_like']:
                post_info['likes_count'] = raw_post_info['likes']['count']
            else:
                post_info['likes_count'] = 'Скрыто'
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK video likes count. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['likes_count'] = f"Ошибка {error_info}"
        
        # Extract views count
        try:
            if 'views' in raw_post_info:
                post_info['views_count'] = raw_post_info['views']
            else:
                post_info['views_count'] = 0
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK video views count. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['views_count'] = f"Ошибка {error_info}"
        
        # Extract links from video description
        post_info["links"] = []
        try:
            post_info["links"] = extractor.find_urls(post_info["text"])
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK video links. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['links'].append(f"Ошибка {error_info}")

        # Extract profile url using owner_id
        post_info['profile_url'] = ""
        try:
            if 'owner_id' in result:
                owner_id = result['owner_id']
                if owner_id < 0:
                    # Negative owner_id means it's a group/community
                    group_id = abs(owner_id)
                    post_info['profile_url'] = f"https://vk.com/club{group_id}?w=club{group_id}"
                else:
                    # Positive owner_id means it's a user
                    post_info['profile_url'] = f"https://vk.com/id{owner_id}"
        except Exception as e:
            error_info = logging_utils.log_error(logger, f"Error extracting VK video profile url. Video url: {result['url']}", e)
            result['debug_info']['errors'].append(error_info)
            post_info['profile_url'] = f"Ошибка {error_info}"

        # Add profile info
        if post_info['profile_url'].startswith("http"):
            post_info = await add_profile_info(post_info, task)

        post_info['processed'] = True

        return post_info, raw_post_info

    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error in 'get_vk_video_info'. Result url: {result.get('url')}", e)
        result['debug_info']['errors'].append(error_info)
        post_info['processed'] = True
        post_info['valid'] = False
        return post_info, raw_post_info