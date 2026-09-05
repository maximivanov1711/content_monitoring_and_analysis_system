import datetime
from apify_client.client import ApifyClientAsync
import os
import dotenv 
import sys

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils

# Setup logger
logger = logging_utils.setup_logger('search_vk.py')

# Load environment variables
dotenv.load_dotenv("././.env", override=True)

async def search_vk(search_vk_parameters):
    final_results = []

    try:
        # Extract parameters from the dictionary
        query = search_vk_parameters["query"]
        start_date = search_vk_parameters["start_date"]
        end_date = search_vk_parameters.get("end_date")
        date_filter = search_vk_parameters.get("date_filter")
        max_results = search_vk_parameters.get("max_results", 999999999)
        
        # Convert start_date and end_date strings to timestamps (dates are in YYYY-MM-DD format)
        start_timestamp = int(datetime.datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        end_timestamp = int(datetime.datetime.strptime(end_date, "%Y-%m-%d").timestamp()) if end_date else None
        
        # Initialize the ApifyClient with your API token
        client = ApifyClientAsync(os.getenv("APIFY_API_KEY2"))
        
        # Define the different filter configurations
        filter_configs = [
            {"filters.kind": "video", "filters.duration": "short"},
            {"filters.kind": "video", "filters.duration": "long"},
            {"filters.kind": "clip", "filters.duration": "short"}
        ]
        
        all_results = []
        
        # Make requests with different filter configurations
        for config in filter_configs:
            # Prepare the Actor input
            run_input = {
                "dev_dataset_clear": False,
                "dev_no_strip": False,
                "filters.hd": False,
                "filters.sort": "update",
                "limit": max_results,
                "query": query
            }
            
            # Add date filter only if specified and valid
            if date_filter in ["day", "week", "month", "year"]:
                run_input["filters.date"] = date_filter
            
            # Update run_input with the specific filter configuration
            run_input.update(config)
            
            # Run the Actor and wait for it to finish
            run = await client.actor("1nSEb9lJnGrwIYQvK").call(run_input=run_input, timeout_secs=9999)
            
            # Fetch results from the run's dataset
            async for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                all_results.append(item)
        
        for item in all_results:
            if (item.get("type") in ["video", "short_video"] and 
                item.get("date", 0) >= start_timestamp and 
                (end_timestamp is None or item.get("date", 0) <= end_timestamp)):

                if item.get("type") == "video":
                    item["post_type"] = "vk_long_video"
                elif item.get("type") == "short_video":
                    item["post_type"] = "vk_short_video"

                final_results.append(item)
    
    except Exception as e:
        logging_utils.log_error(logger, f"Error searching VK. Query: {query}", e)
    
    return final_results
