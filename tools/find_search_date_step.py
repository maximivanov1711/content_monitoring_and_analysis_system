from oxylabs import AsyncClient
import json5
import json
from datetime import datetime, timedelta
import asyncio
import os
import sys

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils

# Configuration constants
TASK_FILES = [
    './search_tasks_ideal/search_dzen_articles_ideal.json',
    './search_tasks_ideal/search_dzen_news_ideal.json',
    './search_tasks_ideal/search_dzen_posts_ideal.json',
    './search_tasks_ideal/search_dzen_shorts_ideal.json',
    './search_tasks_ideal/search_dzen_videos_ideal.json',
    './search_tasks_ideal/search_instagram_posts_ideal.json',
    './search_tasks_ideal/search_instagram_reels_ideal.json',
    './search_tasks_ideal/search_tiktok_photos_ideal.json',
    './search_tasks_ideal/search_tiktok_videos_ideal.json',
    './search_tasks_ideal/search_twitch_all_ideal.json',
    './search_tasks_ideal/search_vk_posts_ideal.json',
    # Add more file paths as needed
]
BATCH_SIZE = 40

# Define time intervals (in days)
TIME_INTERVALS = [360, 240, 120, 90, 60, 40, 30, 20, 15, 10, 7, 5, 4, 3, 2, 1]

# Setup logger
logger = logging_utils.setup_logger(prefix='search_date_step_finder.py')

# Initialize Oxylabs API client
client = AsyncClient("maximivanov1711_oNECR","Iamaxim2004os__")

async def single_search(query, title_filter, url_filter, text_filter, sites, start_date, end_date, udm=None, negative_url_filter=None, negative_title_filter=None):
    search_query = f"{query}"
    
    # Handle title filters
    if title_filter:
        if isinstance(title_filter, list):
            if len(title_filter) > 1:
                title_filter_query = " OR ".join([f"intitle:{filter_item}" for filter_item in title_filter])
                search_query += f" ({title_filter_query})"
            else:
                search_query += f" intitle:{title_filter[0]}"
        else:
            search_query += f" intitle:{title_filter}"
    
    # Handle URL filters
    if url_filter:
        if isinstance(url_filter, list):
            if len(url_filter) > 1:
                url_filter_query = " OR ".join([f"inurl:{filter_item}" for filter_item in url_filter])
                search_query += f" ({url_filter_query})"
            else:
                search_query += f" inurl:{url_filter[0]}"
        else:
            search_query += f" inurl:{url_filter}"
    
    # Handle negative URL filters
    if negative_url_filter:
        if isinstance(negative_url_filter, list):
            for filter_item in negative_url_filter:
                search_query += f" -inurl:{filter_item}"
        else:
            search_query += f" -inurl:{negative_url_filter}"
    
    # Handle negative title filters
    if negative_title_filter:
        if isinstance(negative_title_filter, list):
            for filter_item in negative_title_filter:
                search_query += f" -intitle:{filter_item}"
        else:
            search_query += f" -intitle:{negative_title_filter}"
    
    # Handle text filters
    if text_filter:
        if isinstance(text_filter, list):
            if len(text_filter) > 1:
                text_filter_query = " OR ".join([f"intext:{filter_item}" for filter_item in text_filter])
                search_query += f" ({text_filter_query})"
            else:
                search_query += f" intext:{text_filter[0]}"
        else:
            search_query += f" intext:{text_filter}"
    
    # Combine sites with OR logic
    if sites:
        if isinstance(sites, list) and len(sites) > 1:
            site_filter_query = " OR ".join([f"site:{site}" for site in sites])
            search_query += f" ({site_filter_query})"
        else:
            site = sites[0] if isinstance(sites, list) else sites
            search_query += f" site:{site}"
    
    # Add date parameters - add one day to end_date (exclusive in Google)
    end_date_adjusted = end_date + timedelta(days=1)
    search_query += f" after:{start_date.strftime('%Y-%m-%d')}"
    search_query += f" before:{end_date_adjusted.strftime('%Y-%m-%d')}"
    
    logger.info(f"Searching with interval of {(end_date - start_date).days + 1} days: {search_query}")
    
    final_results = []
    current_page = 1
    
    # Check API limitations
    has_site = 'site:' in search_query
    has_intext = 'intext:' in search_query
    max_pages = 1 if (has_site and has_intext) else 100
    
    while current_page <= max_pages:
        params = {
            "query": search_query,
            "parse": True,
            "start_page": current_page,
            "pages": 1,
            "limit": 100,
            "poll_interval": 3,
            "timeout": 600
        }
        
        if udm is not None:
            params["context"] = [{"key": "udm", "value": udm}]
        
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            response = await client.google.scrape_search(**params)
            if getattr(response, 'results', None):
                break
            logging_utils.log_warning(logger, f"No results on attempt {attempt}/{max_retries}, retrying...")
            await asyncio.sleep(1)
        else:
            logging_utils.log_warning(logger, f"No results after {max_retries} retries, stopping pagination.")
            break
        
        results = response.results[0].content['results']
        if 'organic' not in results:
            logging_utils.log_warning(logger, "No 'organic' field in API response, stopping pagination.")
            break

        organic_results = results['organic']
        final_results.extend(organic_results)
        
        if 'organic_videos' in results:
            final_results.extend(results['organic_videos'])
        
        if not organic_results or current_page >= max_pages:
            break
        current_page += 1
    
    results_count = len(final_results)
    logger.info(f"Found {results_count} results with {(end_date - start_date).days + 1} day interval")
    
    return {
        "days_interval": (end_date - start_date).days + 1,
        "results_count": results_count,
        "final_query": search_query
    }

async def find_optimal_date_step(query, title_filter=None, url_filter=None, text_filter=None, 
                                sites=None, start_date=None, udm=None, negative_url_filter=None, 
                                negative_title_filter=None):
    if start_date is None:
        start_date = datetime.now() - timedelta(days=365)
    elif isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    
    logger.info(f"Finding optimal date step for query: {query}, start date: {start_date}")
    
    for interval in TIME_INTERVALS:
        end_date = start_date + timedelta(days=interval - 1)  # -1 for inclusive interval
        
        result = await single_search(
            query, title_filter, url_filter, text_filter, sites, 
            start_date, end_date, udm, negative_url_filter, negative_title_filter
        )
        
        if result["results_count"] < 100:
            logger.info(f"Found optimal date step: {interval} days with {result['results_count']} results")
            return result
        
        logger.info(f"Results count ({result['results_count']}) > 100, trying smaller interval")
    
    logging_utils.log_warning(logger, "All intervals returned > 100 results. Using smallest interval (1 day).")
    return await single_search(
        query, title_filter, url_filter, text_filter, sites, 
        start_date, start_date, udm, negative_url_filter, negative_title_filter
    )

def load_tasks(task_file):
    with open(task_file, 'r', encoding='utf-8') as f:
        tasks = json5.load(f)
        if not isinstance(tasks, list):
            logger.error(f"Error: Task file {task_file} must contain a JSON array")
            return []
        logger.info(f"Loaded {len(tasks)} tasks from {task_file}")
        return tasks

def flatten_tasks(tasks):
    flattened_tasks = []
    for task_idx, task in enumerate(tasks):
        # Skip disabled tasks
        if not task.get('enabled', True):
            logger.info(f"Skipping disabled task {task_idx+1}")
            continue
            
        # Only process tasks with auto_datesteps: true
        if not task.get('auto_datesteps', False):
            logger.info(f"Skipping task {task_idx+1} without auto_datesteps: true")
            continue
        
        # Get dates from the "dates" array or the "start_date" field
        dates = task.get('dates', [])
        if not dates and 'start_date' in task:
            dates = [task['start_date']]
        
        if not dates:
            logging_utils.log_warning(logger, f"Task {task_idx+1} has no dates specified, skipping")
            continue
        
        for date in dates:
            flattened_tasks.append({
                "task_idx": task_idx,
                "query": task.get('query'),
                "title_filter": task.get('title_filter'),
                "url_filter": task.get('url_filter'),
                "text_filter": task.get('text_filter'),
                "sites": task.get('sites'),
                "start_date": date,
                "udm": task.get('udm'),
                "negative_url_filter": task.get('negative_url_filter'),
                "negative_title_filter": task.get('negative_title_filter')
            })
    
    return flattened_tasks

async def process_tasks(flattened_tasks, batch_size=10):
    results = []
    
    # Process tasks in batches to control concurrency
    for i in range(0, len(flattened_tasks), batch_size):
        batch = flattened_tasks[i:i+batch_size]
        batch_tasks = []
        
        for task in batch:
            coro = find_optimal_date_step(
                task["query"],
                task["title_filter"],
                task["url_filter"],
                task["text_filter"],
                task["sites"],
                task["start_date"],
                task["udm"],
                task["negative_url_filter"],
                task["negative_title_filter"]
            )
            batch_tasks.append(coro)
        
        # Execute batch concurrently
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        # Process batch results
        for j, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.error(f"Task failed: {result}")
                continue
            
            results.append({
                "task_idx": batch[j]["task_idx"],
                "query": batch[j]["query"],
                "start_date": batch[j]["start_date"],
                "source_file": batch[j]["source_file"],
                "result": result
            })
    
    return results

async def main():
    try:
        all_flattened_tasks = []
        file_task_mapping = {}

        # Load tasks from all files
        for task_file in TASK_FILES:
            output_file = f'./search_tasks_ideal_with_datesteps/{os.path.basename(task_file).replace(".json", "_with_datesteps.json")}'
            
            tasks = load_tasks(task_file)
            if not tasks:
                logger.error(f"No valid tasks found in {task_file}")
                continue
            
            # Create a deep copy of tasks for modification
            updated_tasks = json.loads(json.dumps(tasks))
            
            # Find tasks with auto_datesteps: true
            auto_datestep_tasks = []
            for task_idx, task in enumerate(tasks):
                if task.get('auto_datesteps', False) and task.get('enabled', True):
                    auto_datestep_tasks.append(task_idx)
            
            if not auto_datestep_tasks:
                logger.info(f"No tasks with auto_datesteps: true found in {task_file}")
                continue
                
            logger.info(f"Found {len(auto_datestep_tasks)} tasks with auto_datesteps: true in {task_file}")
            
            # Flatten tasks into individual search requests
            flattened_tasks = flatten_tasks(tasks)
            
            # Store file-specific information for later use
            file_task_mapping[task_file] = {
                "tasks": tasks,
                "updated_tasks": updated_tasks,
                "auto_datestep_tasks": auto_datestep_tasks,
                "output_file": output_file
            }
            
            # Tag each flattened task with its source file
            for task in flattened_tasks:
                task["source_file"] = task_file
                
            all_flattened_tasks.extend(flattened_tasks)
            
        if not all_flattened_tasks:
            logging_utils.log_warning(logger, "No tasks to process across all files")
            return
            
        logger.info(f"Processing a total of {len(all_flattened_tasks)} tasks from {len(TASK_FILES)} files")
        
        # Process all tasks concurrently
        results = await process_tasks(all_flattened_tasks, BATCH_SIZE)
        
        # Process results for each file separately
        for task_file, file_info in file_task_mapping.items():
            # Filter results only by source file
            file_results = [r for r in results if r["source_file"] == task_file]
            
            # Update the tasks with new dates format
            for task_idx in file_info["auto_datestep_tasks"]:
                task_results = [r for r in file_results if r["task_idx"] == task_idx]
                
                if not task_results:
                    logging_utils.log_warning(logger, f"No results for task {task_idx} in {task_file}")
                    continue
                    
                # Sort by start_date in descending order (newest first)
                task_results.sort(key=lambda x: x["start_date"], reverse=True)
                
                # Create new dates list with proper format
                new_dates = []
                for i, result in enumerate(task_results):
                    date_entry = {
                        "start_date": result["start_date"],
                        "date_step": result["result"]["days_interval"],
                        "search_query": result["result"]["final_query"],
                        "results_count": result["result"]["results_count"]
                    }
                    
                    # Add end_date for all except the first (newest) date
                    if i > 0:
                        date_entry["end_date"] = task_results[i-1]["start_date"]
                    
                    new_dates.append(date_entry)
                
                # Update the task with new dates
                file_info["updated_tasks"][task_idx]["dates"] = new_dates
            
            # Create output directory if it doesn't exist
            output_dir = os.path.dirname(file_info["output_file"])
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            # Save updated tasks to output file
            with open(file_info["output_file"], 'w', encoding='utf-8') as f:
                json.dump(file_info["updated_tasks"], f, ensure_ascii=False, indent=2)
            logger.info(f"Updated tasks saved to {file_info['output_file']}")
        
        # Print summary
        print(f"Processed {len(results)} search requests from {len(TASK_FILES)} files")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
