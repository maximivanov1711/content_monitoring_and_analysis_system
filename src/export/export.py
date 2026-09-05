import json
import sys
import os
import requests
from datetime import datetime
import asyncio
import re

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils
from src.utils.utils import resolve_date_parameter
from src.notify.notify import notify

# Setup logger
logger = logging_utils.setup_logger('export.py')

# N8N webhook URL for data export as per requirements
WEBHOOK_URL = "https://n8n-srza.onrender.com/webhook/020c69a7-529c-4429-9868-923354006295"
BATCH_SIZE = 500
    

def filter_valid_results(results):
    """
    Filter results to only include valid ones with required fields.
    
    Args:
        results: List of search results
        
    Returns:
        list: Filtered results
    """
    valid_results = []
    
    for result in results:
        is_valid = result.get('post_info', {}).get('valid', True)
        # is_processed = result.get('post_info', {}).get('processed', True)
        is_excluded_profile = result.get('post_info', {}).get('is_excluded_profile', False)
        
        # if is_valid and is_processed and not is_excluded_profile:
        if is_valid and not is_excluded_profile:
            valid_results.append(result)
            continue

        logger.debug(f"Skipping invalid result. Result url: {result.get('url')}")
        logger.debug(f"result: {json.dumps(result['post_info'], ensure_ascii=False, indent=4)}")
    
    return valid_results


def filter_results_by_score(results, score_filter):
    """
    Filter results to only include those with scores in the score_filter list.
    
    Args:
        results: List of search results
        score_filter: List of acceptable scores
        
    Returns:
        list: Filtered results
    """
    if not score_filter:
        return results
    
    filtered_results = []
    
    for result in results:
        score = result.get('score')
        if score in score_filter or not score_filter:
            filtered_results.append(result)
        else:
            logger.debug(f"Skipping result with score {score} not in filter {score_filter}. Result url: {result.get('url')}")
    
    return filtered_results


def format_results(results):
    """
    Format results to match the expected format.
    """
    formatted_results = []

    for result in results:
        try:
            formatted_result = {}

            formatted_result['url'] = result.get('url', '')
            
            formatted_result['publication_date'] = result['post_info'].get('publication_date') or result.get('publication_date', '')
            
            formatted_result['post_type'] = result.get('post_type', '')
            formatted_result['title'] = result['post_info'].get('title') or result.get('title', '')
            formatted_result['text'] = result['post_info'].get('text') or result.get('text', '') 

            if result['post_info'].get('is_excluded_profile', False):
                formatted_result['profile_type'] = 'Исключенный профиль (официальный или дружественный)'
            elif result['post_info'].get('is_editor_profile', False):
                formatted_result['profile_type'] = 'Профиль нарезчика'
            else:
                formatted_result['profile_type'] = ''
            
            links = result['post_info'].get('links') or result.get('links', '')
            if isinstance(links, list) and len(links) == 0:
                formatted_result['links'] = ""
            elif isinstance(links, list):
                links_text = ""
                for link in links:
                    if isinstance(link, dict):
                        links_text += f"{link['title']} - {link['url']}\n\n"
                    else:
                        links_text += f"{link}\n\n"
                formatted_result['links'] = links_text
            
            formatted_result['views_count'] = result['post_info'].get('views_count') or result.get('views_count', '')
            formatted_result['likes_count'] = result['post_info'].get('likes_count') or result.get('likes_count', '')
            formatted_result['comments_count'] = result['post_info'].get('comments_count') or result.get('comments_count', '')
            formatted_result['profile_url'] = result['post_info'].get('profile_url') or result.get('profile_url', '')
            formatted_result['profile_name'] = result['post_info'].get('profile_info', {}).get('profile_name') or result.get('profile_name', '')
            formatted_result['profile_description'] = result['post_info'].get('profile_info', {}).get('profile_description') or result.get('profile_description', '')
            
            if result['post_info'].get('profile_url', ''):
                if 'www.' in result['post_info']['profile_url']:
                    formatted_result['profile_url'] += f"\n{result['post_info']['profile_url'].replace('www.', '')}"
                else:
                    formatted_result['profile_url'] += f"\n{result['post_info']['profile_url'].replace('://', '://www.')}"

            profile_links = result['post_info'].get('profile_info', {}).get('profile_links') or result.get('profile_links', '')
            if isinstance(profile_links, list) and len(profile_links) == 0:
                formatted_result['profile_links'] = ""
            elif isinstance(profile_links, list):
                profile_links_text = ""
                for link in profile_links:
                    if isinstance(link, dict):
                        profile_links_text += f"{link['title']} - {link['url']}\n\n"
                    else:
                        profile_links_text += f"{link}\n\n"
                formatted_result['profile_links'] = profile_links_text

            if result.get('score', '') == 0:
                formatted_result['score'] = "Точно релевантен"
            else:
                formatted_result['score'] = "Возможно релевантен"

            formatted_result['profile_subscribers_count'] = result['post_info'].get('profile_info', {}).get('profile_subscribers_count') or result.get('profile_subscribers_count', '')

            # Format analysis info
            negative_moments = result.get('analysis_info', {}).get('negative_moments', '')
            if isinstance(negative_moments, list) and len(negative_moments) > 0:
                negative_moments_text = ""
                for moment in negative_moments:
                    negative_moments_text += f'"{moment}"\n\n'
                formatted_result['negative_moments'] = negative_moments_text.rstrip('\n\n')
            else:
                formatted_result['negative_moments'] = ''

            if result.get('analysis_info', {}).get('sentiment', '') == 'DANGEROUS':
                formatted_result['sentiment'] = "ПОДОЗРИТЕЛЬНО"
            elif result.get('analysis_info', {}).get('sentiment', '') == 'SAFE':
                formatted_result['sentiment'] = "Безопасно"
            else:
                formatted_result['sentiment'] = ""

            if result.get('subtitles_info', {}):
                if result.get('subtitles_info', {}).get('subtitles_url', ''):
                    formatted_result['subtitles'] = f"Полные субтитры:\n{result.get('subtitles_info', {}).get('subtitles_url', '')}\n\n{result.get('subtitles_info', {}).get('subtitles')[:40000]}... (Полные субтитры по ссылке в начале ячейки)"
                else:
                    formatted_result['subtitles'] = result.get('subtitles_info', {}).get('subtitles', '')
            else:
                formatted_result['subtitles'] = ''

            # TODO: Remove this after testing
            formatted_result['subtitles'] = ''

            important_text = (
                formatted_result.get('title', '') +
                formatted_result.get('text', '') +
                formatted_result.get('profile_description', '') +
                formatted_result.get('links', '') +
                formatted_result.get('profile_links', '')
            )
            if 't.me/BazaArsenMark_bot?start=' in important_text:
                formatted_result['profile_type'] = 'Профиль нарезчика'

            logger.debug(f"Subtitles length: {len(formatted_result['subtitles'])}")

            formatted_results.append(formatted_result)

        except Exception as e:
            logging_utils.log_error(logger, f"Error formatting result. Result url: {result.get('url')}", e)
            continue

    return formatted_results
    


def calculate_statistics_and_notify(results):
    """
    Calculate statistics from results and send notification.
    
    Args:
        results: List of search results
        
    TODO: Fix profile detection - current issues:
    1. May need to use formatted results instead of raw results
    2. Profile data might be nested in post_info.profile_info
    3. Subscriber count filtering might be too strict (should allow > 0 instead of truthy check)
    4. Profile names might be empty strings but profiles still valid
    """
    try:
        # Filter results to only include those with score equal to 0
        score_zero_results = [result for result in results if result.get('score') == 0]
        
        # Calculate total
        total_found = len(score_zero_results)
        
        # Calculate by platform
        platform_counts = {
            'youtube': 0,
            'instagram': 0,
            'tiktok': 0,
            'telegram': 0,
            'twitch': 0,
            'vk': 0,
            'dzen': 0
        }
        
        # Count by platform - only for results with score 0
        for result in score_zero_results:
            post_type = result.get('post_type', '').lower()
            if 'youtube' in post_type:
                platform_counts['youtube'] += 1
            elif 'instagram' in post_type:
                platform_counts['instagram'] += 1
            elif 'tiktok' in post_type:
                platform_counts['tiktok'] += 1
            elif 'telegram' in post_type:
                platform_counts['telegram'] += 1
            elif 'twitch' in post_type:
                platform_counts['twitch'] += 1
            elif 'vk' in post_type:
                platform_counts['vk'] += 1
            elif 'dzen' in post_type:
                platform_counts['dzen'] += 1
        
        # Find top 3 profiles by subscriber count and their most viewed content
        profiles_data = {}
        
        # Get the resolved date for LAST_DAY to filter posts
        target_date = resolve_date_parameter("LAST_DAY")
        
        for i, result in enumerate(score_zero_results):
            # Extract profile data from nested structure
            profile_info = result.get('post_info', {}).get('profile_info', {})
            profile_name = profile_info.get('profile_name', '')
            subscribers_count = profile_info.get('profile_subscribers_count', 0)
            
            # Handle cases where subscriber count is a string like "Неизвестно для личных страниц"
            if isinstance(subscribers_count, str):
                try:
                    subscribers_count = int(subscribers_count)
                except (ValueError, TypeError):
                    subscribers_count = 0
            
            title = result.get('title', '')
            text = result.get('text', '')
            content = title if title else text
            
            # Get views count for this post
            views_count = result.get('post_info', {}).get('views_count', 0)
            if isinstance(views_count, str):
                try:
                    views_count = int(views_count)
                except (ValueError, TypeError):
                    views_count = 0
            
            # Only include posts with not excluded profiles for popular profiles statistics
            # Also exclude posts with dates containing "относительно"
            # Only include posts with publication_date equal to LAST_DAY
            is_excluded_profile = result.get('post_info', {}).get('is_excluded_profile', False)
            publication_date = result.get('post_info', {}).get('publication_date') or result.get('publication_date', '')
            has_relative_date = 'относительно' in str(publication_date).lower()
            is_target_date = str(publication_date) == target_date
            
            if profile_name and subscribers_count > 0 and not is_excluded_profile and not has_relative_date and is_target_date:
                # Group by profile and track most viewed content
                if profile_name not in profiles_data:
                    profiles_data[profile_name] = {
                        'name': profile_name,
                        'subscribers': subscribers_count,
                        'most_viewed_content': content,
                        'most_viewed_url': result.get('url', ''),
                        'most_viewed_count': views_count
                    }
                else:
                    # Update if this post has more views
                    if views_count > profiles_data[profile_name]['most_viewed_count']:
                        profiles_data[profile_name]['most_viewed_content'] = content
                        profiles_data[profile_name]['most_viewed_url'] = result.get('url', '')
                        profiles_data[profile_name]['most_viewed_count'] = views_count
        
        # Sort by subscribers and get top 3
        profiles_with_subs = list(profiles_data.values())
        top_profiles = sorted(profiles_with_subs, key=lambda x: x['subscribers'], reverse=True)[:3]
        
        # Calculate sentiment analysis statistics
        dangerous_count = 0
        safe_count = 0
        
        for result in score_zero_results:
            sentiment = result.get('analysis_info', {}).get('sentiment', '')
            if sentiment == 'DANGEROUS':
                dangerous_count += 1
            elif sentiment == 'SAFE':
                safe_count += 1
        
        # Format notification message
        message = f"""✅ Ежедневный поиск контента выполнен успешно! ✅

<b>Ссылка на таблицу:</b>
https://docs.google.com/spreadsheets/d/15zehNcNtz576PJ22JuyXMvoDDxBYnz1p_lUwyqUBdTY/edit?gid=503339011#gid=503339011

<b>Статистика за вчерашний день:</b>
Всего найдено: {total_found}
Найдено в Youtube: {platform_counts['youtube']}
Найдено в Instagram: {platform_counts['instagram']}
Найдено в Tiktok: {platform_counts['tiktok']}
Найдено в Telegram: {platform_counts['telegram']}
Найдено в Twitch: {platform_counts['twitch']}
Найдено в VK: {platform_counts['vk']}
Найдено в Dzen: {platform_counts['dzen']}

<b>Статистика анализа:</b>
Всего подозрительного контента - {dangerous_count}
Всего безопасного контента - {safe_count}

<b>Самые популярные профили, выложившие видео:</b>"""
        
        for i, profile in enumerate(top_profiles, 1):
            content = profile['most_viewed_content']
            content = content.replace('\n', ' ').replace('\r', ' ')
            if len(content) > 100:
                content = content[:100] + '...'
            if i == 1:
                message += f"\n{i}. <a href=\"{profile['most_viewed_url']}\"><b>Ссылка</b></a>. <b>Автор</b>: {profile['name']} ({int(profile['subscribers'])} подписчиков): <b>Название</b>: {content}"
            else:
                message += f"\n\n{i}. <a href=\"{profile['most_viewed_url']}\"><b>Ссылка</b></a>. <b>Автор</b>: {profile['name']} ({int(profile['subscribers'])} подписчиков): <b>Название</b>: {content}"
        
        # Send notification
        notify(message, "public")
        logger.info("Export completion notification sent successfully")
        
    except Exception as e:
        logging_utils.log_error(logger, f"Error sending export notification", e)


def sort_results_for_export(results):
    """
    Sort results by:
    1. Publication date descending (only for dates in YYYY-MM-DD format)
    2. Score ascending
    3. Views count descending
    
    Args:
        results: List of formatted results
        
    Returns:
        list: Sorted results
    """
    def sort_key(result):
        # Extract publication date and check if it's in YYYY-MM-DD format
        pub_date = result.get('publication_date', '')
        date_for_sort = None
        
        # Check if date matches YYYY-MM-DD format using regex
        if re.match(r'^\d{4}-\d{2}-\d{2}$', str(pub_date)):
            try:
                date_for_sort = datetime.strptime(pub_date, '%Y-%m-%d')
            except ValueError:
                date_for_sort = None
        
        # Extract score
        score = result.get('score', 0)
        if score == '':
            score = 0
        try:
            score = int(score)
        except (ValueError, TypeError):
            score = 0
        
        # Extract views count
        views_count = result.get('views_count', 0)
        if views_count == '':
            views_count = 0
        try:
            views_count = int(views_count)
        except (ValueError, TypeError):
            views_count = 0
        
        # Return sort key tuple
        # For date: None comes last, then dates in descending order (negate for desc)
        # For score: ascending order
        # For views: descending order (negate for desc)
        if date_for_sort is None:
            return (1, score, -views_count)  # None dates go to end
        else:
            return (0, -date_for_sort.timestamp(), score, -views_count)
    
    return sorted(results, key=sort_key)


async def export(results, task={}):
    """
    Export data to webhook and save locally.
    
    Args:
        data: Search results to export (can be list or dict)
        
    Returns:
        bool: True if export was successful, False otherwise
    """

    try:
        # Filter valid results
        valid_results = filter_valid_results(results)

        # Filter results by score if score_filter is provided
        score_filter = task.get('export_parameters', {}).get('score_filter')
        score_filtered_results = filter_results_by_score(valid_results, score_filter)

        # Format results only if specified in task parameters
        if task.get('export_parameters', {}).get('format_results', True):
            export_results = format_results(score_filtered_results)
        else:
            export_results = score_filtered_results
        
        # Sort results before sending to webhook
        export_results = sort_results_for_export(export_results)
        
        for i in range(0, len(export_results), BATCH_SIZE):
            payload = {
                "results": export_results[i:i + BATCH_SIZE],
                "table_id": task.get('export_parameters', {}).get('table_id'),
                "unofficial_content_sheet_id": task.get('export_parameters', {}).get('unofficial_content_sheet_id'),
                "editors_content_sheet_id": task.get('export_parameters', {}).get('editors_content_sheet_id'),
                "youtube_content_sheet_id": task.get('export_parameters', {}).get('youtube_content_sheet_id'),
            }

            logger.debug(f"Payload: {json.dumps(payload, ensure_ascii=False, indent=4)}")

            try:
                # Send data to webhook
                response = requests.post(
                    WEBHOOK_URL,
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                )
                
                response.raise_for_status()
                
                # Add 1 second delay between webhook calls
                await asyncio.sleep(1)
                
            except Exception as e:
                logging_utils.log_error(logger, f"Error sending export batch", e)
                continue
        
        # Send notification after successful export
        calculate_statistics_and_notify(score_filtered_results)
        
    except Exception as e:
        logging_utils.log_error(logger, f"Error during export", e)