import aiohttp
import sys
import asyncio

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import utils
from src.utils import logging_utils
from src.add_subtitles import add_subtitles_utils

# Setup logger
logger = logging_utils.setup_logger(prefix="parse_subtitles.py")

# Rate limiting configuration by API endpoint
YOUTUBE_TRANSCRIPTOR_DELAY = 0.15
TIKTOK_API_DELAY = 0.15
VIDEO_TRANSCRIPT_SCRAPER_DELAY = 0.3

# Global semaphores for rate limiting (binary semaphores) by API endpoint
YOUTUBE_TRANSCRIPTOR_SEMAPHORE = asyncio.Semaphore(1)
TIKTOK_API_SEMAPHORE = asyncio.Semaphore(1)
VIDEO_TRANSCRIPT_SCRAPER_SEMAPHORE = asyncio.Semaphore(1)


async def parse_subtitles(result, task={}):
    url = result['url']
    post_type = result['post_type']
    
    # Handle YouTube video subtitles using YouTube Transcriptor API
    if post_type == "youtube_video":
        video_id = utils.extract_youtube_video_id(url)

        api_url = f"https://youtube-transcriptor.p.rapidapi.com/transcript"
        headers = {
            "x-rapidapi-host": "youtube-transcriptor.p.rapidapi.com",
            "x-rapidapi-key": "ebfc131555msh1b99dcb2063f177p1350d6jsnc0cc0c9bcbcc"
        }
        params = {"video_id": video_id}

        # Make API request to get YouTube video transcript (retry up to 3 times)
        subtitles_info = None
        for attempt in range(3):
            async with YOUTUBE_TRANSCRIPTOR_SEMAPHORE:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(api_url, headers=headers, params=params) as response:
                            response.raise_for_status()
                            api_response = await response.json()

                            if not api_response or not isinstance(api_response, list) or len(api_response) == 0:
                                return {}

                            subtitles_info = api_response[0]

                            if "transcription" not in subtitles_info or "lengthInSeconds" not in subtitles_info:
                                return {}

                            break
                except Exception as e:
                    logging_utils.log_warning(logger, f"Error using YouTube Transcriptor API (attempt {attempt + 1}/3). post url: {url}")
                    if attempt == 2:
                        raise
                finally:
                    await asyncio.sleep(YOUTUBE_TRANSCRIPTOR_DELAY)

        # Format subtitles with timestamps
        formatted_subtitles = add_subtitles_utils.format_subtitles_with_timestamps(
            subtitles_info["transcription"], 
            subtitle_text_key="subtitle"
        )

        duration = int(subtitles_info["lengthInSeconds"])
        return {
            "subtitles": formatted_subtitles,
            "duration": duration
        }

    # Handle TikTok and VK video subtitles
    if post_type in ["tiktok_video", "vk_long_video", "vk_short_video"]:
        subtitle_language = None

        # For TikTok videos, first get available subtitle languages
        if post_type == "tiktok_video":
            api_url = f"https://tiktok-api23.p.rapidapi.com/api/post/detail"
            headers = {
                "x-rapidapi-host": "tiktok-api23.p.rapidapi.com",
                "x-rapidapi-key": "ebfc131555msh1b99dcb2063f177p1350d6jsnc0cc0c9bcbcc"
            }
            params = {"videoId": url}

            for attempt in range(3):
                async with TIKTOK_API_SEMAPHORE:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(api_url, headers=headers, params=params) as response:
                                response.raise_for_status()
                                tiktok_data = await response.json()

                                if not tiktok_data or "itemInfo" not in tiktok_data or "itemStruct" not in tiktok_data["itemInfo"] or "video" not in tiktok_data["itemInfo"]["itemStruct"] or "subtitleInfos" not in tiktok_data["itemInfo"]["itemStruct"]["video"]:
                                    return {}

                                subtitle_infos = tiktok_data["itemInfo"]["itemStruct"]["video"]["subtitleInfos"]

                                for info in subtitle_infos:
                                    if info["LanguageCodeName"] == "rus-RU":
                                        subtitle_language = "rus-RU"
                                        break
                                if subtitle_language is None:
                                    for info in subtitle_infos:
                                        if info["LanguageCodeName"] == "eng-US":
                                            subtitle_language = "eng-US"
                                            break

                                break
                    except Exception as e:
                        logging_utils.log_warning(logger, f"Error using TikTok API (attempt {attempt + 1}/3). post url: {url}")
                        if attempt == 2:
                            raise
                    finally:
                        await asyncio.sleep(TIKTOK_API_DELAY)

        # Use video transcript scraper API for actual subtitle extraction
        transcript_url = "https://video-transcript-scraper.p.rapidapi.com/"
        transcript_headers = {
            "Content-Type": "application/json",
            "x-rapidapi-host": "video-transcript-scraper.p.rapidapi.com",
            "x-rapidapi-key": "ebfc131555msh1b99dcb2063f177p1350d6jsnc0cc0c9bcbcc"
        }

        payload = {"video_url": url}
        if subtitle_language:
            payload["language"] = subtitle_language

        # Make API request to get video transcript (retry up to 3 times)
        for attempt in range(3):
            async with VIDEO_TRANSCRIPT_SCRAPER_SEMAPHORE:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(transcript_url, headers=transcript_headers, json=payload) as response:
                            response.raise_for_status()
                            subtitles_info = await response.json()
                            break
                except Exception as e:
                    logging_utils.log_warning(logger, f"Error using Video Transcript Scraper API (attempt {attempt + 1}/3). post url: {url}")
                    if attempt == 2:
                        raise
                finally:
                    await asyncio.sleep(VIDEO_TRANSCRIPT_SCRAPER_DELAY)

        # Format subtitles with timestamps
        formatted_subtitles = add_subtitles_utils.format_subtitles_with_timestamps(
            subtitles_info["transcript"], 
            subtitle_text_key="text"
        )

        result = {
            "subtitles": formatted_subtitles,
            "duration": subtitles_info["duration"]
        }

        return result

    # Return None for unsupported post types
    return None