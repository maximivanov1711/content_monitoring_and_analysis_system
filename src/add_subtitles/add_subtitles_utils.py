import sys
import os
import aiohttp
import dotenv

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils
from src.utils import utils


# Load environment variables
dotenv.load_dotenv(dotenv_path='./.env', override=True)

# Setup logger
logger = logging_utils.setup_logger(prefix="add_subtitles_utils.py")


async def upload_to_github_gist(text_content, filename, description):
    """
    Upload text content to GitHub Gist and return the raw URL.
    
    Args:
        text_content: The text to upload
        filename: Name for the file (optional)
        description: Description for the gist (optional)
    
    Returns:
        str: GitHub Gist raw URL if successful, None if failed
    """
    try:
        api_url = "https://api.github.com/gists"
        
        # Prepare the payload for GitHub API
        payload = {
            "description": description,
            "public": False,  # Private gist
            "files": {
                filename: {
                    "content": text_content
                }
            }
        }
        
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {os.environ.get('GITHUB_API_KEY')}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as response:
                response.raise_for_status()
                
                gist_data = await response.json()
                # Get the raw_url from the file data
                raw_url = gist_data["files"][filename]["raw_url"]
                logger.info(f"Successfully uploaded subtitles to GitHub Gist. 'raw_url': {raw_url}, 'description': {description}")
                return raw_url
                    
    except Exception as e:
        logging_utils.log_error(logger, f"Error uploading subtitles to GitHub Gist. 'description': {description}", e)
        return None


def format_subtitles_with_timestamps(subtitles_data, subtitle_text_key="text"):
    """
    Format subtitles with timestamps from subtitle data.
    
    Args:
        subtitles_data: List of subtitle items with start time and text
        subtitle_text_key: Key to extract text from each subtitle item ("text" or "subtitle")
        
    Returns:
        str: Formatted subtitles string with timestamps
    """
    formatted_subtitles = ""
    
    for item in subtitles_data:
        start_time = utils.format_timecode(item["start"])
        subtitle_text = item.get(subtitle_text_key, "")
        
        if formatted_subtitles:
            formatted_subtitles += f" ({start_time}) {subtitle_text}"
        else:
            formatted_subtitles = f"({start_time}) {subtitle_text}"
    
    return formatted_subtitles