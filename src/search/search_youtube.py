import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
import sys

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils

# Constants
REQUEST_DELAY = 1  # Delay in seconds between search requests

# Setup logger
logger = logging_utils.setup_logger("search_youtube.py")


def filter_items(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Map raw API items into the minimal schema.
    If a field is missing, set its value to "Отсутствует".
    If viewCount exists but cannot be converted, leave its original value.
    """
    filtered = []
    for item in raw_items:
        page_item: Dict[str, Any] = {}

        # type
        try:
            page_item["type"] = item["type"]
        except KeyError:
            page_item["type"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error extracting type", e)
            page_item["type"] = f"Не найдено {error_info}"

        # videoId
        try:
            page_item["video_id"] = item["videoId"]
        except KeyError:
            page_item["video_id"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error extracting videoId", e)
            page_item["video_id"] = f"Не найдено {error_info}"

        # title
        try:
            page_item["title"] = item["title"]
        except KeyError:
            page_item["title"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error extracting title", e)
            page_item["title"] = f"Не найдено {error_info}"

        # channelTitle
        try:
            page_item["channel_title"] = item["channelTitle"]
        except KeyError:
            page_item["channel_title"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error extracting channelTitle", e)
            page_item["channel_title"] = f"Не найдено {error_info}"

        # channelId
        try:
            page_item["channel_id"] = item["channelId"]
        except KeyError:
            page_item["channel_id"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error extracting channelId", e)
            page_item["channel_id"] = f"Не найдено {error_info}"

        # channelHandle
        try:
            page_item["channel_handle"] = item["channelHandle"]
        except KeyError:
            page_item["channel_handle"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error extracting channelHandle", e)
            page_item["channel_handle"] = f"Не найдено {error_info}"

        # description
        try:
            page_item["description"] = item["description"]
        except KeyError:
            page_item["description"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error extracting description", e)
            page_item["description"] = f"Не найдено {error_info}"

        # viewCount (convert to int if possible)
        try:
            if "viewCount" in item:
                try:
                    page_item["view_count"] = int(item["viewCount"])
                except Exception:
                    page_item["view_count"] = item["viewCount"]
            else:
                page_item["view_count"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error extracting viewCount", e)
            page_item["view_count"] = f"Не найдено {error_info}"

        # publishDate
        try:
            page_item["publish_date"] = item["publishDate"]
        except KeyError:
            page_item["publish_date"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error extracting publishDate", e)
            page_item["publish_date"] = f"Не найдено {error_info}"

        # lengthText
        try:
            page_item["length_text"] = item["lengthText"]
        except KeyError:
            page_item["length_text"] = "Отсутствует"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error extracting lengthText", e)
            page_item["length_text"] = f"Не найдено {error_info}"

        # URL for this video
        try:
            page_item["url"] = f"https://www.youtube.com/watch?v={page_item['video_id']}"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error constructing video URL", e)
            page_item["url"] = f"Не найдено {error_info}"

        # Profile URL for the channel
        try:
            page_item["profile_url"] = f"https://www.youtube.com/{page_item['channel_handle']}"
        except Exception as e:
            error_info = logging_utils.log_error(logger, "Error constructing profile URL", e)
            page_item["profile_url"] = f"Не найдено {error_info}"

        filtered.append(page_item)

    return filtered

async def search(
    session: aiohttp.ClientSession,
    query: str,
    video_type: str,
    duration: str,
    sort_by: str,
    token: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    url = "https://yt-api.p.rapidapi.com/search"
    
    params = {
        "query": query,
        "type": video_type,
        "duration": duration,
        "sort_by": sort_by
    }
    
    if token:
        params["token"] = token
    
    headers = {
        "x-rapidapi-host": "yt-api.p.rapidapi.com",
        "x-rapidapi-key": "ebfc131555msh1b99dcb2063f177p1350d6jsnc0cc0c9bcbcc"
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.info(
                f"search_youtube: query={query!r}, type={video_type}, duration={duration}, sort_by={sort_by}, attempt={attempt + 1}"
            )
            async with session.get(url, params=params, headers=headers) as response:
                response.raise_for_status()
                result = await response.json()
                return result
        except Exception as e:
            if attempt == max_retries - 1:
                logging_utils.log_error(
                    logger,
                    f"search_youtube final error after {max_retries} attempts for query={query!r}, type={video_type}, duration={duration}, sort_by={sort_by}",
                    e
                )
                return None
            else:
                logger.warning(
                    f"search_youtube retry {attempt + 1}/{max_retries} failed for query={query!r}, type={video_type}, duration={duration}, sort_by={sort_by}. Error: {str(e)}"
                )
                await asyncio.sleep(2 ** attempt)

async def get_all_results(
    session: aiohttp.ClientSession,
    query: str,
    video_type: str,
    duration: str,
    sort_by: str,
    max_pages: Optional[int],
    start_date: Optional[str] = None
) -> Dict[str, Any]:
    # Modify query to include start_date if provided
    if start_date:
        query = f"{query} after:{start_date}"
    
    logger.info(f"get_all_results: start query={query!r}, type={video_type}, duration={duration}, sort_by={sort_by}")
    all_results = []
    token = None
    page = 1
    
    # Fetch first page and append it
    logger.info(f"get_all_results: fetching page {page} for query={query!r}, type={video_type}, duration={duration}, sort_by={sort_by}")
    response = await search(session, query, video_type, duration, sort_by, token)
    if response is None:
        logger.warning(f"get_all_results: search failed for first page, skipping query={query!r}, type={video_type}, duration={duration}, sort_by={sort_by}")
        return {
            "search_query": query,
            "type": video_type,
            "duration": duration,
            "sort_by": sort_by,
            "results": []
        }
    raw_items = response.get("data", [])
    if raw_items:
        page_items = filter_items(raw_items)
        all_results.extend(page_items)
    # Paginate and append each subsequent page
    while response.get("continuation") and (max_pages is None or page < max_pages):
        token = response["continuation"]
        page += 1
        logger.info(f"get_all_results: fetching page {page} for query={query!r}, type={video_type}, duration={duration}, sort_by={sort_by}")
        response = await search(session, query, video_type, duration, sort_by, token)
        if response is None:
            logger.warning(f"get_all_results: search failed for page {page}, stopping pagination for query={query!r}, type={video_type}, duration={duration}, sort_by={sort_by}")
            break
        raw_items = response.get("data", [])
        if raw_items:
            page_items = filter_items(raw_items)
            all_results.extend(page_items)

    logger.info(
        f"get_all_results: completed query={query!r}, type={video_type}, "
        f"duration={duration}, sort_by={sort_by}, total_items={len(all_results)}"
    )
    return {
        "search_query": query,
        "type": video_type,
        "duration": duration,
        "sort_by": sort_by,
        "results": all_results
    }

async def search_youtube(
    search_youtube_parameters: Dict[str, Any]
) -> List[Dict[str, Any]]:
    search_queries = search_youtube_parameters["query"]
    max_pages = search_youtube_parameters.get("max_pages")
    start_date = search_youtube_parameters.get("start_date")
    max_results = search_youtube_parameters.get("max_results", 999999999)
    
    logger.info(f"process_search_queries: start with queries={search_queries}")
    
    all_results = []
    
    async with aiohttp.ClientSession() as session:
        sort_by_options = ["relevance", "rating", "date", "views"]
        
        task_count = 0
        total_tasks = len(search_queries) * len(sort_by_options) * 4  # 4 combinations per sort_by
        
        for query in search_queries:
            for sort_by in sort_by_options:
                # Execute tasks sequentially with delays
                combinations = [
                    ("video", "short"),
                    ("video", "medium"), 
                    ("video", "long"),
                    ("shorts", "short")
                ]
                
                for video_type, duration in combinations:
                    if task_count > 0:  # Don't delay before the first request
                        await asyncio.sleep(REQUEST_DELAY)
                    
                    task_count += 1
                    logger.info(f"Executing task {task_count}/{total_tasks}")
                    
                    result = await get_all_results(session, query, video_type, duration, sort_by, max_pages, start_date)
                    
                    # Process results immediately instead of storing tasks
                    for item in result["results"]:
                        video_id = item.get("video_id")
                        item_type = item.get("type")
                        
                        # Only include items with type="video" and deduplicate
                        if video_id and item_type == "video":
                            # Check if we've already seen this video_id
                            already_exists = any(existing_item.get("video_id") == video_id for existing_item in all_results)
                            if not already_exists:
                                # Add search parameters to each item
                                item["query"] = search_youtube_parameters.copy()
                                item["query"].update({
                                    "search_final_query": result["search_query"],
                                    "search_type": result["type"],
                                    "search_duration": result["duration"],
                                    "search_sort_by": result["sort_by"]
                                })
                                all_results.append(item)
        
        logger.info(f"process_search_queries: total unique videos with type='video' found: {len(all_results)}")
    
    if len(all_results) > max_results:
        all_results = all_results[:max_results]

    return all_results
