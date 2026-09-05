import asyncio
import json
import aiohttp
from datetime import datetime, timedelta
import sys
import os
import dotenv

dotenv.load_dotenv()

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils

# Setup logger
logger = logging_utils.setup_logger(prefix="search_telegram.py")

async def search_telegram(search_telegram_options: dict) -> list:
    # Extract options from dict
    query = search_telegram_options['query']
    start_date = search_telegram_options['start_date']
    max_results = search_telegram_options.get("max_results", 999999999)
    
    # If query is a list, concatenate with " | "
    if isinstance(query, list):
        query = " | ".join(query)
    
    # Parse start date and calculate end date (start_date + 1 day)
    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
    end_date_obj = start_date_obj + timedelta(days=1)
    end_date = end_date_obj.strftime("%Y-%m-%d")
    
    # API endpoint and headers
    url = "https://api.telemetr.me/channels/posts/search"
    headers = {
        "Authorization": f"Bearer {os.getenv('TELEMETR_API_KEY')}"
    }
    
    all_items = []
    
    async with aiohttp.ClientSession() as session:
        # Make initial request to get total count
        initial_params = {
            "peerType": "channel",
            "query": query,
            "startDate": start_date,
            "endDate": end_date,
            "limit": max_results,
            "hideDeleted": 1
        }
        
        async with session.get(url, headers=headers, params=initial_params) as response:
            response.raise_for_status()
                
            data = await response.json()
            
            items = data["response"]["items"]
            all_items.extend(items)
            total_count = data["response"]["total_count"]
            
            # Calculate number of pages needed (if we need more than the first page)
            tasks = []
            offset = len(all_items)
            
            while offset < total_count:
                params = {
                    "peerType": "channel",
                    "query": query,
                    "startDate": start_date,
                    "endDate": end_date,
                    "limit": 50,
                    "offset": offset,
                    "hideDeleted": 1
                }
                tasks.append(fetch_page(session, url, headers, params))
                offset += 50
            
            # Run all requests concurrently if more pages exist
            if tasks:
                results = await asyncio.gather(*tasks)
                for result in results:
                    all_items.extend(result)
            
            # Convert items to search result format
            formatted_items = []

            for item in all_items:
                # Fix url
                item['url'] = f'https://{item["link"]}'

                # Skip private channels
                if '/joinchat/' in item['url']:
                    continue

                # Set post type for processing
                item['post_type'] = 'telegram_post'

                formatted_items.append(item)
            
            return formatted_items

async def fetch_page(session, url, headers, params):
    try:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                return []
                
            data = await response.json()
            if data["status"] != "ok":
                return []
                
            items = data["response"]["items"]
            return items
    except Exception:
        return []