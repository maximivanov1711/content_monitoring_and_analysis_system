import re
import json5 
import json
import sys
import requests
from urlextract import URLExtract
from urllib.parse import unquote
from datetime import datetime, timedelta

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils

# Setup logger
logger = logging_utils.setup_logger("utils.py")

def load_mock_results(mock_results_path):
    """
    Load mock results from JSON file.
    
    Args:
        mock_results_path (str): Path to the mock results JSON file
        
    Returns:
        list: Mock search results
    """
    with open(mock_results_path, 'r', encoding='utf-8') as file:
        mock_results = load_json(file)
    return mock_results

def resolve_date_parameter(date_value):
    """
    Resolve a date parameter, handling relative date strings like "LAST_DAY".
    
    Args:
        date_value: Date value (string)
        
    Returns:
        str: Resolved date in YYYY-MM-DD format
    """
    if isinstance(date_value, str):
        if date_value.upper() == "LAST_DAY":
            yesterday = datetime.now() - timedelta(days=1)
            return yesterday.strftime("%Y-%m-%d")
        elif date_value.upper() == "LAST_WEEK":
            last_week = datetime.now() - timedelta(days=7)
            return last_week.strftime("%Y-%m-%d")
        elif date_value.upper() == "LAST_MONTH":
            last_month = datetime.now() - timedelta(days=30)
            return last_month.strftime("%Y-%m-%d")
        else:
            try:
                datetime.strptime(date_value, "%Y-%m-%d")
                return date_value
            except ValueError:
                yesterday = datetime.now() - timedelta(days=1)
                return yesterday.strftime("%Y-%m-%d")
    else:
        yesterday = datetime.now() - timedelta(days=1)
        return yesterday.strftime("%Y-%m-%d")

def load_json(file):
    """
    Load JSON from a file, trying json5 first and falling back to regular json.
    
    Args:
        file: File object to read from
        
    Returns:
        Parsed JSON data
    """
    try:
        return json.load(file)
    except Exception as e:
        logger.warning(f"json parsing failed: {e}, falling back to json5")
        file.seek(0)  # Reset file pointer
        return json5.load(file)

def extract_youtube_video_id(url):
    """Extract YouTube video ID from various URL formats."""
    if not url:
        return None
    
    url = str(url)
    
    # Handle youtu.be short URLs
    if "youtu.be/" in url:
        start_idx = url.find("youtu.be/") + 9
        video_id = url[start_idx:start_idx + 11]
        if len(video_id) == 11:
            return video_id
    
    # Handle youtube.com URLs
    if "youtube.com" in url:
        # Handle shorts URLs
        if "/shorts/" in url:
            start_idx = url.find("/shorts/") + 8
            video_id = url[start_idx:start_idx + 11]
            if len(video_id) == 11:
                return video_id
        
        # Handle watch URLs with v parameter
        if "v=" in url:
            start_idx = url.find("v=") + 2
            end_idx = start_idx + 11
            # Check for additional parameters after video ID
            for char in ["&", "?", "#"]:
                char_idx = url.find(char, start_idx)
                if char_idx != -1 and char_idx < end_idx:
                    end_idx = char_idx
            video_id = url[start_idx:end_idx]
            if len(video_id) == 11:
                return video_id
        
        # Handle embed URLs
        if "/embed/" in url:
            start_idx = url.find("/embed/") + 7
            video_id = url[start_idx:start_idx + 11]
            if len(video_id) == 11:
                return video_id
    
    return None

def determine_post_type(url):
    """
    Determine the content type based on URL.
    
    Args:
        url (str): URL to analyze
        
    Returns:
        str: Content type for processing
    """
    url = str(url).lower()
    
    # Check for different platform URLs
    # Telegram content type detection
    if "t.me" in url:
        return "telegram_post"

    # Instagram content type detection
    if "instagram.com" in url:
        if "/reel/" in url:
            return "instagram_reels"
        elif "/p/" in url:
            return "instagram_post"

    # YouTube content type detection
    if "youtube.com" in url:
        if "youtube.com/shorts/" in url:
            return "youtube_shorts"
        elif "youtube.com/post/" in url:
            return "youtube_post"
        elif "youtube.com/watch?" in url:
            return "youtube_video"

    # TikTok content type detection
    if "tiktok.com" in url:
        if "/video/" in url:
            return "tiktok_video"
        elif "/photo/" in url:
            return "tiktok_photo"

    # VK content type detection
    if "vk.com" in url:
        if "vk.com/wall" in url:
            return "vk_post"
        elif "vk.com/video" in url:
            return "vk_long_video"
        elif "vk.com/clip" in url:
            return "vk_short_video"

    # Twitch content type detection
    if "twitch.tv" in url:
        if "clip" in url:
            return "twitch_video"
        elif "video" in url:
            return "twitch_stream"

    # Dzen content type detection
    if "dzen.ru" in url:
        if "dzen.ru/a/" in url:
            return "dzen_article"
        elif "dzen.ru/news/" in url:
            return "dzen_news"
        elif "dzen.ru/video/" in url:
            return "dzen_long_video"
        elif "dzen.ru/shorts/" in url:
            return "dzen_short_video"
        elif "dzen.ru/b/" in url:
            return "dzen_post"

    if "https://" in url or "http://" in url:
        return "web_page"
    
    return "unknown"

def parse_number(input_text):
    """
    Convert text representations of numbers like '15.7K', '3,5 тыс', '2 million', '1,2 млн', '5.3B', '4 млрд' to integers.
    
    Args:
        number_text (str): Text representation of a number
        
    Returns:
        int: The converted integer value, or original string if conversion fails.
    """

    if isinstance(input_text, int) or isinstance(input_text, float):
        return input_text

    text = input_text.strip().lower().replace(' ', '').replace(',', '.')
    suffix_multipliers = {
        # thousands
        'тысяч': 1_000,
        'тысяча': 1_000,
        'тыс.': 1_000,
        'тыс': 1_000,
        'thousands': 1_000,
        'thousand': 1_000,
        'k': 1_000,
        # millions
        'миллионов': 1_000_000,
        'миллион': 1_000_000,
        'млн.': 1_000_000,
        'млн': 1_000_000,
        'millions': 1_000_000,
        'million': 1_000_000,
        'm': 1_000_000,
        # billions
        'миллиардов': 1_000_000_000,
        'миллиард': 1_000_000_000,
        'млрд.': 1_000_000_000,
        'млрд': 1_000_000_000,
        'billions': 1_000_000_000,
        'billion': 1_000_000_000,
        'bn': 1_000_000_000,
        'b': 1_000_000_000
    }
    try:
        # Check for any known suffix, longest first to avoid partial matches
        for suffix, factor in sorted(suffix_multipliers.items(),
                                     key=lambda x: -len(x[0])):
            if text.endswith(suffix):
                num_part = text[:-len(suffix)]
                if num_part.endswith('.'):
                    num_part = num_part[:-1]
                num = float(num_part) if num_part else 1.0
                return int(num * factor)
        # No suffix: parse as a plain number
        return int(float(text))
    except Exception:
        return input_text

def format_timecode(seconds):
    hours, remainder = divmod(float(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

def format_transcript(output):
    # If no output data is available, return empty string
    if not output or "text" not in output:
        return ""
        
    # Get the full transcript text
    full_text = output["text"].strip()
    
    # If no sentence timestamps available, return the full text without timestamps
    if "sentence_level_timestamps" not in output or not output["sentence_level_timestamps"]:
        return f"(00:00:00) {full_text}"
    
    # Create a list of sentences with their positions and timestamps
    timestamped_sentences = []
    for sentence in output["sentence_level_timestamps"]:
        text = sentence["text"].strip()
        if not text:
            continue
            
        # Find this sentence in the full text
        pos = full_text.find(text)
        if pos >= 0:
            timestamped_sentences.append({
                "text": text,
                "position": pos,
                "length": len(text),
                "start": sentence["start"]
            })
    
    # Sort sentences by their position in the text
    timestamped_sentences.sort(key=lambda x: x["position"])
    
    # Build the formatted output
    result = ""
    last_end = 0
    
    # Check if there's text before the first timestamped sentence
    if timestamped_sentences and timestamped_sentences[0]["position"] > 0:
        # Add (00:00:00) to the first part of text
        first_text = full_text[:timestamped_sentences[0]["position"]].strip()
        if first_text:
            result += f"(00:00:00) {first_text}"
            if not result.endswith(" "):
                result += " "
            last_end = timestamped_sentences[0]["position"]
    
    # If we haven't added any text yet and there are timestamped sentences
    if not result and timestamped_sentences:
        # First sentence already has a timestamp, no need to add (00:00:00)
        pass
    # If we haven't added any text and there are no timestamped sentences with positions
    elif not result:
        # Add (00:00:00) to the beginning of the full text
        result = f"(00:00:00) {full_text}"
        return result.strip()
    
    for sentence in timestamped_sentences:
        # If there's text before this timestamped sentence, add it without timestamp
        if sentence["position"] > last_end:
            text_between = full_text[last_end:sentence["position"]].strip()
            if text_between:
                result += text_between
                if not result.endswith(" "):
                    result += " "
        
        # Add the timestamped sentence
        start_time = format_timecode(sentence["start"])
        result += f"({start_time}) {sentence['text']}"
        
        # Add space if needed
        if not result.endswith(" "):
            result += " "
        
        # Update the last position
        last_end = sentence["position"] + sentence["length"]
    
    # Add any remaining text after the last timestamped sentence
    if last_end < len(full_text):
        remainder = full_text[last_end:].strip()
        if remainder:
            if result and not result.endswith(" "):
                result += " "
            result += remainder
    
    return result.strip()

def normalize_url(url: str, remove_query_params: bool = True) -> str:
    """
    Normalize URLs by stripping off query‐strings except for special cases.
    """

    # VK URL normalization
    url = url.replace("https://m.vk.com", "https://vk.com")
    
    # Add https:// if url doesn't start with https:// or http://
    if not url.startswith("https://") and not url.startswith("http://"):
        url = "https://" + url

    # Strip query‐strings except for special cases
    if remove_query_params and "/fv?to" not in url and "youtube.com/watch?v=" not in url and "https://vk.com/feed" not in url:
        url = url.split("?")[0]

    # Twitch URL normalization
    if "twitch.tv" in url:
        if "/clip/" in url:
            clip_id = url.split("/clip/")[1]
            return f"https://clips.twitch.tv/{clip_id}"
        
        if "/videos/" in url:
            video_id = url.split("/videos/")[1]
            return f"https://twitch.tv/videos/{video_id}"

    # Instagram URL normalization
    if "instagram.com" in url:
        # Check if URL is already in canonical form for posts
        post_match = re.search(r'https://(?:www\.)instagram\.com/p/([^/?]+)/?(?:\?.*)?$', url)
        if post_match:
            post_id = post_match.group(1)
            return f"https://instagram.com/p/{post_id}/"
        
        # Check if URL is already in canonical form for reels
        reel_match = re.search(r'https://(?:www\.)?instagram\.com/reel/([^/?]+)/?(?:\?.*)?$', url)
        if reel_match:
            reel_id = reel_match.group(1)
            return f"https://instagram.com/reel/{reel_id}/"
        
        # Handle URLs with username in path for posts
        post_match = re.search(r'https://(?:www\.)?instagram\.com/[^/]+/p/([^/?]+)', url)
        if post_match:
            post_id = post_match.group(1)
            return f"https://instagram.com/p/{post_id}/"
        
        # Handle URLs with username in path for reels
        reel_match = re.search(r'https://(?:www\.)?instagram\.com/[^/]+/reel/([^/?]+)', url)
        if reel_match:
            reel_id = reel_match.group(1)
            return f"https://instagram.com/reel/{reel_id}/"

    return url

def load_excluded_profiles():
    """
    Load excluded profiles from the excluded_profiles.json file.
    
    Returns:
        A list of excluded profile URLs
    """
    global EXCLUDED_PROFILES

    try:
        with open("data/excluded_profiles.json5", "r", encoding="utf-8") as f:
            excluded_profiles_data = json5.load(f)
        
        # Combine all platform excluded profiles into a single list
        all_excluded_profiles = []
        for platform, profiles in excluded_profiles_data.items():
            for profile in profiles:
                all_excluded_profiles.append(profile.lower().strip())
        
        EXCLUDED_PROFILES = all_excluded_profiles
    except Exception as e:
        logging_utils.log_error(logger, "Error loading excluded profiles", e)
        EXCLUDED_PROFILES = []

def load_editor_profiles():
    """
    Load editor profiles from the n8n webhook.
    
    Returns:
        A list of editor profile URLs
    """
    global EDITOR_PROFILES

    try:
        response = requests.get(
            "https://n8n-srza.onrender.com/webhook/229f7b22-cd0c-42e9-bde2-3cf013abde92"
        )
        response.raise_for_status()
        webhook_data = response.json()

        extractor = URLExtract()
        all_editor_profiles = []

        for item in webhook_data:
            if not isinstance(item, dict):
                continue

            for key, raw_value in item.items():
                if not isinstance(raw_value, str):
                    continue

                key_lower = key.lower()
                if not any(platform in key_lower for platform in ['ютуб', 'инстаграм', 'тик-ток']):
                    continue

                value = raw_value.lower()
                # logger.info(f"\nProcessing field '{key}': {value}")

                # 1) Extract and canonicalize any raw URLs first:
                found_links = []
                urls = extractor.find_urls(value)
                for url in urls:
                    # Handle case where URLExtract returns tuples
                    if isinstance(url, tuple):
                        url = url[0]
                    # Normalize and strip query parameters
                    clean = unquote(url.split('?')[0])
                    clean = clean.replace('//www.', '//')
                    found_links.append(clean)
                    # remove the entire URL (including any leftover ?‑params) from `value`
                    value = value.replace(url, ' ')

                # 2) Now strip any remaining "?..." fragments just in case
                value = re.sub(r'\?[^ ]+', ' ', value)

                # 3) Extract candidate "words" and skip any that start with "_" or contain no letters
                words = re.findall(r'[A-Za-z0-9_./-]+', value)
                # logger.info(f"EXTRACTED ENGLISH WORDS: {words}")

                for word in words:
                    # drop purely param‑looking tokens
                    if word.startswith('_'):
                        continue
                    if not re.search(r'[A-Za-z]', word):
                        continue

                    # build platform‑specific URLs
                    key_lower = key.lower()
                    profile = None
                    if 'ютуб' in key_lower:
                        if word.startswith('channel/'):
                            profile = f"https://www.youtube.com/{word}"
                        else:
                            profile = f"https://www.youtube.com/@{word}"
                    elif 'инстаграм' in key_lower:
                        profile = f"https://instagram.com/{word}/"
                    elif 'тик-ток' in key_lower:
                        profile = f"https://tiktok.com/@{word}/"

                    if profile:
                        profile = unquote(profile)
                        all_editor_profiles.append(profile)
                        # logger.info(f"Created profile URL from word '{word}': {profile}")
                
                formatted_links = []
                for link in found_links:
                    url_prefixes = {
                                    'https://www.youtube.com/': 'https://www.youtube.com/',
                                    'https://www.youtube.com/': 'https://www.youtube.com/',
                                    'http://www.youtube.com/': 'https://www.youtube.com/',
                                    'http://www.youtube.com/': 'https://www.youtube.com/',
                                    'www.youtube.com/': 'https://www.youtube.com/',
                                    'youtube.com/': 'https://www.youtube.com/',
                                    'https://www.instagram.com/': 'https://instagram.com/',
                                    'https://instagram.com/': 'https://instagram.com/',
                                    'http://www.instagram.com/': 'https://instagram.com/',
                                    'http://instagram.com/': 'https://instagram.com/',
                                    'www.instagram.com/': 'https://instagram.com/',
                                    'instagram.com/': 'https://instagram.com/',
                                    'https://www.tiktok.com/': 'https://tiktok.com/',
                                    'https://tiktok.com/': 'https://tiktok.com/',
                                    'http://www.tiktok.com/': 'https://tiktok.com/',
                                    'http://tiktok.com/': 'https://tiktok.com/',
                                    'www.tiktok.com/': 'https://tiktok.com/',
                                    'tiktok.com/': 'https://tiktok.com/'
                                }
                    for prefix, replacement in url_prefixes.items():
                        if link.startswith(prefix):
                            link = link.replace(prefix, replacement)
                            break
                    formatted_links.append(link)

                # logger.info(f"Found links: {formatted_links}")

                all_editor_profiles.extend(formatted_links)

        # Ensure Instagram and TikTok URLs end with "/"
        normalized_profiles = []
        for profile in all_editor_profiles:
            if ('instagram.com' in profile or 'tiktok.com' in profile) and not profile.endswith('/'):
                profile = profile + '/'
            normalized_profiles.append(profile)

        # logger.info(f"Final editor profiles list: {normalized_profiles}")
        EDITOR_PROFILES = normalized_profiles

    except Exception as e:
        logging_utils.log_error(logger, "Error loading editor profiles from webhook", e)
        EDITOR_PROFILES = []

def is_excluded_profile(url: str) -> bool:
    """
    Check if a URL is from an excluded profile.

    Args:
        url: The URL to check

    Returns:
        True if the URL starts with any excluded-profile prefix, False otherwise
    """
    if url.endswith('/'):
        url = url[:-1]

    for excluded_profile in EXCLUDED_PROFILES:
        if excluded_profile.lower().strip() == url.lower().strip() or excluded_profile.replace('://', '://www.').lower().strip() == url.lower().strip():
            return True
    return False

def is_editor_profile(result: dict) -> bool:
    """
    Check if a URL is from an editor profile.

    Args:
        url: The URL to check

    Returns:
        True if the URL starts with any editor-profile prefix, False otherwise
    """
    url = result.get('profile_url', '')
    if url.endswith('/'):
        url = url[:-1]

    for editor_profile in EDITOR_PROFILES:
        if editor_profile.lower().strip() == url.lower().strip() or editor_profile.replace('://', '://www.').lower().strip() == url.lower().strip():
            return True
    
    text = result.get('post_info', {}).get('text', '') + result.get('post_info', {}).get('title', '') + result.get('profile_info', {}).get('profile_description', '')

    if 't.me/BazaArsenMark_bot?start=' in text:
        return True

    return False

# Load excluded profiles once at module load
EXCLUDED_PROFILES = []
EDITOR_PROFILES = []


if __name__ == "__main__":
    load_excluded_profiles()
    load_editor_profiles()
    youtube_profiles = [profile for profile in EDITOR_PROFILES if 'youtube.com' in profile]
    logger.info(f"EDITOR_PROFILES (YouTube only): {youtube_profiles}")
    
    tiktok_profiles = [profile for profile in EDITOR_PROFILES if 'tiktok.com' in profile]
    logger.info(f"EDITOR_PROFILES (TikTok only): {tiktok_profiles}")
    
    instagram_profiles = [profile for profile in EDITOR_PROFILES if 'instagram.com' in profile]
    logger.info(f"EDITOR_PROFILES (Instagram only): {instagram_profiles}")
    
    vk_profiles = [profile for profile in EDITOR_PROFILES if 'vk.com' in profile]
    logger.info(f"EDITOR_PROFILES (VK only): {vk_profiles}")
    
    dzen_profiles = [profile for profile in EDITOR_PROFILES if 'dzen.ru' in profile]
    logger.info(f"EDITOR_PROFILES (Dzen only): {dzen_profiles}")
    
    twitch_profiles = [profile for profile in EDITOR_PROFILES if 'twitch.tv' in profile]
    logger.info(f"EDITOR_PROFILES (Twitch only): {twitch_profiles}")
    
    telegram_profiles = [profile for profile in EDITOR_PROFILES if 't.me' in profile]
    logger.info(f"EDITOR_PROFILES (Telegram only): {telegram_profiles}")