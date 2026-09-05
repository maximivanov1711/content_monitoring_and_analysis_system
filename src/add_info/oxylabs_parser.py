"""
Module for making Oxylabs API requests to fetch raw HTML content.
"""
import os
import base64
import sys
import aiohttp
import asyncio
import dotenv
import json

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils


# Load environment variables
dotenv.load_dotenv(dotenv_path='./.env', override=True)

MAX_RETRIES = 5
RETRY_DELAY = 0

# Configure logging with timestamped filename
logger = logging_utils.setup_logger('oxylabs_parser.py')


async def get_raw_html(url, wait_time=None):
    """
    Async function to get raw HTML using Oxylabs REST API.
    
    Args:
        url (str): The URL to scrape
        wait_time (int): Number of seconds to wait for lazy-loaded content
        
    Returns:
        str: Raw HTML content from the response
    """
    retry_delay = RETRY_DELAY

    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                logging_utils.log_warning(logger, f"Retrying Oxylabs API request. Attempt {attempt+1}/{MAX_RETRIES}")

            # Create basic auth credentials
            auth = base64.b64encode(f"{os.getenv('OXYLABS_USERNAME')}:{os.getenv('OXYLABS_PASSWORD')}".encode()).decode()
            
            # Build request payload
            payload = {
                "url": url,
                "source": "universal",
                "render": "html",
                "user_agent_type": "desktop_chrome",
                "locale": "ru-ru",
                "timeout": 10000,
                "context": [
                    {
                        "key": "http_method",
                        "value": "get"
                    },
                    {
                        "key": "follow_redirects",
                        "value": True
                    }
                ]
            }
            
            # Add wait time if specified
            if wait_time is not None:
                payload["browser_instructions"] = [
                    {
                        "type": "wait",
                        "wait_time_s": wait_time
                    }
                ]
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10000)) as session:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {auth}"
                }
                    
                async with session.post(
                    "https://realtime.oxylabs.io/v1/queries",
                    json=payload,
                    headers=headers
                ) as response:
                    response_json = await response.json()

                    # Handle non-200 response
                    if response.status != 200:
                        logging_utils.log_warning(logger, f"Received non-200 response:\n{json.dumps(response_json, indent=4, ensure_ascii=False)} Url: {url}")
                        
                        # Handle timed out error
                        if response_json and "timed out" in response_json.get('message', '').lower():
                            if wait_time is not None and wait_time > 1:
                                wait_time = max(1, wait_time - 1)
                                logging_utils.log_warning(logger, f"Detected timed out error, decrementing wait_time by 1 second. Url: {url}")
                                continue
                        # Handle other errors
                        else:
                            continue
                    
                    # Handle empty results
                    if len(response_json.get('results', [])) == 0:
                        logging_utils.log_warning(logger, f"No results found in response:\n{json.dumps(response_json, indent=4, ensure_ascii=False)} Url: {url}")
                        continue
                    
                    # Handle result status code
                    result_status_code = response_json["results"][0].get("status_code", 200)
                    if result_status_code >= 400:
                        retry_delay += 1
                        logging_utils.log_warning(logger, f"Result has {result_status_code} status code (server error), retrying in {retry_delay} seconds. Url: {url}")
                        await asyncio.sleep(retry_delay)
                        continue
                    
                    return response_json
        
        except Exception as e:
            logging_utils.log_error(logger, f"Error in 'oxylabs_parser.get_raw_html()'. 'url': {url}, 'wait_time': {wait_time}", e)
            return None
        
    logging_utils.log_error(logger, f"Max retries reached in 'oxylabs_parser.get_raw_html()'. 'url': {url}")
    return None