from oxylabs import AsyncClient
import json5
from datetime import datetime, timedelta
import asyncio
import sys
import os

import dotenv

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils

# Configuration constants
BATCH_SIZE = 30

# Setup logger
logger = logging_utils.setup_logger(prefix='search_google.py')

dotenv.load_dotenv("././.env", override=True)

# Initialize Oxylabs API client
client = AsyncClient(os.getenv("OXYLABS_USERNAME"),
                     os.getenv("OXYLABS_PASSWORD"))


def get_timestamp():
    """Get current timestamp formatted for filenames"""
    return datetime.now().strftime('%Y%m%d%H%M%S')


async def single_search(query,
                        title_filter,
                        url_filter,
                        text_filter,
                        sites,
                        start_date,
                        end_date=None,
                        udm=None,
                        save_raw=True,
                        negative_url_filter=None,
                        negative_title_filter=None):
    """Perform a single search for multiple sites and date range"""
    # Set default dates based on requirements
    today = datetime.now()

    # Store original parameter values to check if they were provided
    original_start_date = start_date
    original_end_date = end_date

    # Case 1: If neither start_date nor end_date provided
    if start_date is None and end_date is None:
        start_date = datetime.strptime("2000-01-01", '%Y-%m-%d')
        end_date = today
    # Case 2: If only start_date provided
    elif start_date is not None and end_date is None:
        end_date = today
    # Case 3: If only end_date provided
    elif start_date is None and end_date is not None:
        start_date = datetime.strptime("2000-01-01", '%Y-%m-%d')

    # Always add one day to end_date to include it in the range (since Google search uses before: as exclusive)
    end_date_adjusted = end_date + timedelta(days=1)

    search_query = f"{query}"

    # Handle title filters
    if title_filter:
        if isinstance(title_filter, list):
            if len(title_filter) > 1:
                title_filter_query = " OR ".join(
                    [f"intitle:{filter_item}" for filter_item in title_filter])
                search_query += f" ({title_filter_query})"
            else:
                search_query += f" intitle:{title_filter[0]}"
        else:
            search_query += f" intitle:{title_filter}"

    # Handle URL filters
    if url_filter:
        if isinstance(url_filter, list):
            if len(url_filter) > 1:
                url_filter_query = " OR ".join(
                    [f"inurl:{filter_item}" for filter_item in url_filter])
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
                text_filter_query = " OR ".join(
                    [f"intext:{filter_item}" for filter_item in text_filter])
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

    # Add date parameters only when at least one date was provided
    if original_start_date is not None or original_end_date is not None:
        search_query += f" after:{start_date.strftime('%Y-%m-%d')}"
        search_query += f" before:{end_date_adjusted.strftime('%Y-%m-%d')}"

    date_range_str = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"

    logger.info(f"single_search started: query='{search_query}'")
    logger.info(f"Final search query being sent to API: '{search_query}'")
    logger.info(
        f"Search parameters - sites: {sites}, udm: {udm}, date_range: {date_range_str}"
    )

    final_results = []
    current_page = 1

    # Check if both site: and intext: are present in query (API limitation)
    has_site = 'site:' in search_query
    has_intext = 'intext:' in search_query
    max_pages = 1 if (
        has_site and has_intext
    ) else 100  # Limit to first page when both operators are used

    if has_site and has_intext:
        logger.info(
            f"API limitation detected: both 'site:' and 'intext:' operators present, limiting to 1 page"
        )

    # Paginate through all available results
    while current_page <= max_pages:
        logger.info(
            f"Fetching page {current_page} for sites: {sites} on {date_range_str}"
        )

        # Create parameters for API request
        params = {
            "query": search_query,
            "parse": True,
            "start_page": current_page,
            "pages": 1,
            "limit": 100,
            "poll_interval": 3,
            "timeout": 600
        }

        # Add context with udm parameter if specified
        if udm is not None:
            params["context"] = [{"key": "udm", "value": udm}]
            logger.info(f"Added udm parameter: {udm}")

        logger.debug(f"API request parameters: {params}")

        # Retry up to 5 times if API returns no results
        max_retries = 1
        response = None
        for attempt in range(1, max_retries + 1):
            logger.info(f"API request attempt {attempt}/{max_retries}")
            try:
                response = await client.google.scrape_search(**params)
                logger.info(f"API response received on attempt {attempt}")

                # Log response structure
                if hasattr(response, 'results') and response.results:
                    logger.info(
                        f"Response has {len(response.results)} result objects")
                    if response.results[0].content:
                        content_keys = list(response.results[0].content.keys())
                        logger.info(f"Response content keys: {content_keys}")
                    else:
                        logging_utils.log_warning(
                            logger, f"Response results[0] has no content")
                else:
                    logging_utils.log_warning(
                        logger,
                        f"API response has no results attribute or results is empty"
                    )
                    logger.debug(f"Response attributes: {dir(response)}")

                if getattr(response, 'results', None):
                    logger.info(
                        f"Valid response received on attempt {attempt}")
                    break
                else:
                    logging_utils.log_warning(
                        logger,
                        f"No results returned by API on attempt {attempt}/{max_retries}, retrying..."
                    )
            except Exception as e:
                logging_utils.log_error(
                    logger,
                    f"API request failed on attempt {attempt}/{max_retries}: {str(e)}",
                    e)
                response = None

            if attempt < max_retries:
                await asyncio.sleep(1)
        else:
            logging_utils.log_warning(
                logger,
                f"No results after {max_retries} retries, stopping pagination."
            )
            break

        if not response or not getattr(response, 'results', None):
            logging_utils.log_error(
                logger, f"Failed to get valid response after all retries")
            break

        # Process results
        try:
            results = response.results[0].content['results']
            logger.info(f"Extracted results object from API response")
        except (IndexError, KeyError, TypeError) as e:
            logging_utils.log_error(
                logger,
                f"Failed to extract results from API response: {str(e)}", e)
            logger.debug(
                f"Response structure: {response.results if hasattr(response, 'results') else 'No results attr'}"
            )
            break

        # Bail out if there's no organic field
        if 'organic' not in results:
            logging_utils.log_warning(
                logger,
                "No 'organic' field in API response, stopping pagination.")
            logger.info(f"Available fields in results: {list(results.keys())}")
            break

        organic_results = results['organic']
        logger.info(
            f"Found {len(organic_results)} organic results on page {current_page}"
        )

        # Filter each result to only include specified fields
        organic_results = [
            filter_result_fields(result) for result in organic_results
        ]

        # Add video results if available
        if 'organic_videos' in results:
            filtered_video_results = [
                filter_result_fields(result)
                for result in results['organic_videos']
            ]
            organic_results.extend(filtered_video_results)
            logger.info(f"Added {len(filtered_video_results)} video results")

        final_results.extend(organic_results)
        logger.info(
            f"Page {current_page} processed: {len(organic_results)} results added, total so far: {len(final_results)}"
        )

        # Break if no more results, reached API limit, or at max pages
        if len(organic_results) < 80 or current_page >= max_pages:
            if len(organic_results) < 80:
                logger.info(
                    f"Stopping pagination: page {current_page} returned only {len(organic_results)} results (less than 80)"
                )
            elif current_page >= max_pages:
                logger.info(
                    f"Stopping pagination: reached max pages ({max_pages})")
            break
        current_page += 1

    logger.info(
        f"single_search completed: sites='{sites}', date_range='{date_range_str}'. Found {len(final_results)} results"
    )
    logger.info(
        f"SEARCH RESULTS SUMMARY - Query: '{search_query}' - Total Results: {len(final_results)}"
    )

    if len(final_results) > 200 and ("-intitle:" not in search_query and
                                     ("after:" in search_query
                                      or "before:" in search_query)):
        logging_utils.log_warning(
            logger,
            f"WARNING: Found {len(final_results)} results for query '{search_query}', which exceeds the recommended maximum of 150 results"
        )

    return {
        "sites": sites,
        "date_range": date_range_str,
        "final_query": search_query,
        "results": final_results
    }


def filter_result_fields(result):
    """Filter result to only include specified fields"""
    filtered_result = {}
    fields_to_keep = [
        'url', 'title', 'desc', 'url_shown', 'favicon_text', 'additional_info'
    ]
    for field in fields_to_keep:
        if field in result:
            filtered_result[field] = result[field]
    return filtered_result


def get_date_range(start_date_str, end_date_str=None):
    """Generate a list of dates between start and end dates"""
    # If no start date provided, use 2000-01-01
    if start_date_str is None:
        start_date = datetime.strptime("2000-01-01", '%Y-%m-%d')
    else:
        # Handle both string and datetime object inputs
        if isinstance(start_date_str, str):
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            start_date = start_date_str

    # If no end date provided, use today
    if end_date_str is None:
        end_date = datetime.now()
    else:
        # Handle both string and datetime object inputs
        if isinstance(end_date_str, str):
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        else:
            end_date = end_date_str

    # Generate list of all dates in the range
    date_list = []
    current_date = start_date
    while current_date <= end_date:
        date_list.append(current_date)
        current_date += timedelta(days=1)

    return date_list


async def _search_google_internal(query,
                                  title_filter=None,
                                  url_filter=None,
                                  text_filter=None,
                                  sites=None,
                                  start_date=None,
                                  end_date=None,
                                  udm=None,
                                  date_step=0,
                                  save_raw=False,
                                  negative_url_filter=None,
                                  negative_title_filter=None):
    """Internal function to perform searches across multiple sites and dates"""
    logger.info(
        f"search started: query='{query}', date range: {start_date} to {end_date}, date_step: {date_step}, save_raw: {save_raw}"
    )

    # Track whether dates were originally provided
    dates_provided = (start_date is not None or end_date is not None)

    # Generate date range
    date_range = get_date_range(start_date, end_date)
    search_tasks = []

    # Handle date_step=0 special case - make one request for the entire date range
    if date_step == 0:
        if dates_provided:
            # Use the first date as the start and the last as the end for the entire range
            if date_range:
                range_start = date_range[0]
                range_end = date_range[-1]
                search_tasks.append((range_start, range_end))
        else:
            # Special case: If no dates provided and date_step=0,
            # we pass None values to indicate no dates were explicitly provided
            search_tasks.append((None, None))
    else:
        # Group dates by the step size
        for i in range(0, len(date_range), date_step):
            # Get a chunk of dates based on date_step
            date_chunk = date_range[i:i + date_step]
            if date_chunk:
                # Use the first date as the start and the last as the end (or just the same date if one day)
                chunk_start = date_chunk[0]
                chunk_end = date_chunk[-1]
                search_tasks.append((chunk_start, chunk_end))

    # Process tasks in batches
    logger.info(
        f"Processing {len(search_tasks)} search tasks in batches of {BATCH_SIZE}"
    )

    date_results = []

    for i in range(0, len(search_tasks), BATCH_SIZE):
        batch = search_tasks[i:i + BATCH_SIZE]
        batch_id = f"{i//BATCH_SIZE + 1}/{(len(search_tasks) + BATCH_SIZE - 1)//BATCH_SIZE}"
        logger.info(f"Processing batch {batch_id} ({len(batch)} tasks)")

        # Create and process batch
        batch_tasks = [
            single_search(query, title_filter, url_filter, text_filter, sites,
                          chunk_start, chunk_end, udm, save_raw,
                          negative_url_filter, negative_title_filter)
            for chunk_start, chunk_end in batch
        ]
        batch_results = await process_batch(batch_tasks)

        # Update results structure
        for result in batch_results:
            if result is not None:  # Check explicitly for None, not just falsy values
                date_results.append({
                    "date_range":
                    result["date_range"],
                    "date_results_count":
                    len(result["results"]),
                    "final_query":
                    result["final_query"],
                    "date_results":
                    result["results"]
                })
                logger.info(
                    f"Added batch result: {len(result['results'])} results for range '{result['date_range']}'"
                )
            else:
                logging_utils.log_warning(
                    logger,
                    f"Batch contained None result - this indicates an exception occurred during processing"
                )

    # Count total results for this query
    query_results_count = sum(
        result["date_results_count"]
        for result in date_results) if date_results else 0

    logger.info(
        f"search finished: Found {query_results_count} results across all date ranges"
    )

    # Add detailed log of total results by query

    return {
        "query_results_count": query_results_count,
        "query_results": date_results
    }


async def search_google(search_parameters):
    """
    Perform Google search using the provided parameters dictionary.
    
    Args:
        search_parameters (dict): Dictionary containing search parameters with the same structure as task JSON files.
            Supported parameters:
            - query (str): The search query
            - title_filter (str/list): Filter for page titles
            - url_filter (str/list): Filter for URLs
            - text_filter (str/list): Filter for page text
            - sites (str/list): Sites to search within
            - negative_url_filter (str/list): URLs to exclude
            - negative_title_filter (str/list): Titles to exclude
            - udm (int): User data mode parameter
            - save_raw (bool): Whether to save raw API responses
            - dates (list): List of date configurations, each containing:
                - start_date (str): Start date in YYYY-MM-DD format
                - end_date (str): End date in YYYY-MM-DD format
                - date_step (int): Number of days to group together (0 for entire range)
            OR traditional date parameters:
            - start_date (str): Start date in YYYY-MM-DD format
            - end_date (str): End date in YYYY-MM-DD format
            - date_step (int): Number of days to group together (0 for entire range)
    
    Returns:
        list: Flat list of search results
    """
    logger.info(
        f"search_google called with parameters: query='{search_parameters.get('query')}', sites={search_parameters.get('sites')}, url_filter={search_parameters.get('url_filter')}"
    )

    # Make a copy to avoid modifying the original
    params = search_parameters.copy()

    # Extract main parameters
    query = params.get('query')
    if not query:
        logging_utils.log_error(logger, "Missing required 'query' parameter")
        raise ValueError("'query' parameter is required")

    title_filter = params.get('title_filter')
    url_filter = params.get('url_filter')
    text_filter = params.get('text_filter')
    sites = params.get('sites')
    udm = params.get('udm')
    save_raw = params.get('save_raw', False)
    negative_url_filter = params.get('negative_url_filter')
    negative_title_filter = params.get('negative_title_filter')

    logger.info(
        f"Extracted parameters - query: '{query}', title_filter: {title_filter}, text_filter: {text_filter}, udm: {udm}, save_raw: {save_raw}"
    )

    # Handle date configurations
    date_configurations = []

    if 'dates' in params:
        # Use the new dates array format
        date_configurations = params['dates']
        logger.info(
            f"Using dates array format with {len(date_configurations)} configurations"
        )
    else:
        # Use traditional date parameters if provided
        single_date_config = {}
        for param in ['start_date', 'end_date', 'date_step']:
            if param in params:
                single_date_config[param] = params[param]

        # Only add to configurations if at least one date parameter was provided
        if single_date_config:
            date_configurations = [single_date_config]
            logger.info(
                f"Using traditional date parameters: {single_date_config}")

    # If no date configurations, add one empty config (no date filtering)
    if not date_configurations:
        date_configurations = [{}]
        logger.info(
            "No date configurations provided, using empty config (no date filtering)"
        )

    # Collect all results
    all_results = []

    # Process each date configuration
    for config_idx, date_config in enumerate(date_configurations):
        logger.info(
            f"Processing date configuration {config_idx + 1}/{len(date_configurations)}: {date_config}"
        )

        # Extract date parameters from this config
        start_date = date_config.get('start_date')
        end_date = date_config.get('end_date')
        date_step = date_config.get('date_step', 0)

        # Convert date strings to datetime objects if provided
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            logger.info(f"Converted start_date to: {start_date}")
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            logger.info(f"Converted end_date to: {end_date}")

        # Perform the search
        logger.info(
            f"Calling _search_google_internal for config {config_idx + 1}")
        result = await _search_google_internal(
            query=query,
            title_filter=title_filter,
            url_filter=url_filter,
            text_filter=text_filter,
            sites=sites,
            start_date=start_date,
            end_date=end_date,
            udm=udm,
            date_step=date_step,
            save_raw=save_raw,
            negative_url_filter=negative_url_filter,
            negative_title_filter=negative_title_filter)

        logger.info(
            f"Date configuration {config_idx + 1} returned {result['query_results_count']} total results across {len(result['query_results'])} date ranges"
        )

        # Flatten results from this date configuration
        for date_result in result['query_results']:
            date_range = date_result['date_range']
            final_query = date_result['final_query']
            results_count = len(date_result['date_results'])

            logger.info(
                f"Processing date range '{date_range}' with {results_count} results (final query: '{final_query}')"
            )

            # Add metadata to each individual result
            for item in date_result['date_results']:
                # Add search metadata to each result - save ALL original search parameters
                item['query'] = search_parameters.copy()
                item['query'].update({
                    "search_final_query":
                    final_query,
                    "search_date_range":
                    date_range,
                    "search_date_step":
                    date_step,
                    "actual_start_date":
                    date_config.get('start_date'),
                    "actual_end_date":
                    date_config.get('end_date')
                })
                all_results.append(item)

    logger.info(
        f"search_google completed: returning {len(all_results)} total results")

    return all_results


async def process_batch(batch_tasks):
    """Process a batch of search tasks with up to BATCH_SIZE concurrent executions and 0.5s delay between each task completion"""
    results = []
    # Initialize with None values to preserve task order
    results = [None] * len(batch_tasks)
    queue = asyncio.Queue()

    # Add tasks to queue with their index to track order
    for i, task in enumerate(batch_tasks):
        await queue.put((i, task))

    async def worker():
        while not queue.empty():
            try:
                idx, task_coro = await queue.get()
                try:
                    result = await task_coro
                    results[idx] = result  # Store result at the correct index
                    logger.info(
                        f"Worker completed task {idx + 1} successfully")
                except Exception as e:
                    logging_utils.log_error(
                        logger,
                        f"Worker task {idx + 1} failed with error: {str(e)}",
                        e)
                    logging_utils.log_error(
                        logger, f"Task {idx + 1} failed with error: {e}", e)
                    results[
                        idx] = None  # Explicitly set to None for failed tasks
                finally:
                    queue.task_done()
                    await asyncio.sleep(
                        1.0
                    )  # Increased delay to 1.0 second to avoid rate limiting
            except asyncio.CancelledError:
                break

    # Create BATCH_SIZE workers
    workers = [asyncio.create_task(worker()) for _ in range(BATCH_SIZE)]
    await queue.join()

    # Cancel workers when done
    for worker_task in workers:
        worker_task.cancel()

    # Remove any None values in case some tasks failed
    return [r for r in results if r is not None]


def load_tasks(task_files):
    """Load search tasks from JSON files with task name information"""
    all_tasks = []
    for task_file in task_files:
        with open(task_file, 'r', encoding='utf-8') as f:
            tasks = json5.load(f)
            if not isinstance(tasks, list):
                logging_utils.log_error(
                    logger,
                    f"Error: Task file {task_file} must contain a JSON array",
                    None)
                continue

            # Extract task name from filename (e.g., "task1.json" -> "task1")
            task_name = os.path.splitext(os.path.basename(task_file))[0]

            # Add task name to each task
            for task in tasks:
                task['_task_name'] = task_name

            all_tasks.extend(tasks)
            logger.info(f"Loaded {len(tasks)} tasks from {task_file}")
    return all_tasks


async def flatten_all_tasks(tasks, default_save_raw=False):
    """Convert all tasks into a flat list of individual search requests"""
    all_search_requests = []

    for task_idx, task_params in enumerate(tasks):
        task_name = task_params.pop('_task_name', f"task{task_idx+1}")

        # Check if task is enabled (default is True)
        if not task_params.pop('enabled', True):
            logger.info(
                f"Skipping disabled task {task_idx+1}/{len(tasks)} from {task_name}"
            )
            continue

        # Store original params (before removing resume)
        params_copy = task_params.copy()

        # Remove resume parameter if present
        if 'resume' in task_params:
            task_params.pop('resume')

        # Add save_raw parameter from command line or task params (default to False if not specified)
        if 'save_raw' not in task_params:
            task_params['save_raw'] = default_save_raw

        # Handle new dates array format
        date_configurations = []

        if 'dates' in task_params:
            # Use the new dates array format
            date_configurations = task_params.pop('dates')
        else:
            # Use traditional date parameters if provided
            single_date_config = {}
            for param in ['start_date', 'end_date', 'date_step']:
                if param in task_params:
                    single_date_config[param] = task_params.pop(param)

            # Only add to configurations if at least one date parameter was provided
            if single_date_config:
                date_configurations = [single_date_config]

        # If no date configurations, add one empty config (no date filtering)
        if not date_configurations:
            date_configurations = [{}]

        # Generate search requests for each date configuration
        for date_config in date_configurations:
            # Extract parameters for this search
            query = task_params['query']
            title_filter = task_params.get('title_filter')
            url_filter = task_params.get('url_filter')
            text_filter = task_params.get('text_filter')
            sites = task_params.get('sites')
            udm = task_params.get('udm')
            save_raw = task_params.get('save_raw', False)
            negative_url_filter = task_params.get('negative_url_filter')
            negative_title_filter = task_params.get('negative_title_filter')

            # Extract date parameters from this config
            start_date = date_config.get('start_date')
            end_date = date_config.get('end_date')
            date_step = date_config.get('date_step', 0)

            # Track whether dates were originally provided
            dates_provided = (start_date is not None or end_date is not None)

            # Generate date range
            date_range = get_date_range(start_date,
                                        end_date) if dates_provided else []
            search_tasks = []

            # Handle date_step=0 special case - make one request for the entire date range
            if date_step == 0:
                if dates_provided:
                    # Use the first date as the start and the last as the end for the entire range
                    if date_range:
                        range_start = date_range[0]
                        range_end = date_range[-1]
                        search_tasks.append((range_start, range_end))
                else:
                    # Special case: If no dates provided, pass None values
                    search_tasks.append((None, None))
            else:
                # Group dates by the step size
                for i in range(0, len(date_range), date_step):
                    # Get a chunk of dates based on date_step
                    date_chunk = date_range[i:i + date_step]
                    if date_chunk:
                        # Use the first date as the start and the last as the end
                        chunk_start = date_chunk[0]
                        chunk_end = date_chunk[-1]
                        search_tasks.append((chunk_start, chunk_end))

            # Create search request objects with task metadata
            for chunk_start, chunk_end in search_tasks:
                search_request = {
                    "task_name": task_name,
                    "task_idx": task_idx,
                    "original_params": params_copy,
                    "search_params": {
                        "query": query,
                        "title_filter": title_filter,
                        "url_filter": url_filter,
                        "text_filter": text_filter,
                        "sites": sites,
                        "start_date": chunk_start,
                        "end_date": chunk_end,
                        "udm": udm,
                        "save_raw": save_raw,
                        "negative_url_filter": negative_url_filter,
                        "negative_title_filter": negative_title_filter
                    }
                }
                all_search_requests.append(search_request)

    return all_search_requests


async def process_all_search_requests(all_search_requests):
    """Process all search requests in batches of BATCH_SIZE"""
    all_results = []

    for i in range(0, len(all_search_requests), BATCH_SIZE):
        batch = all_search_requests[i:i + BATCH_SIZE]
        batch_id = f"{i//BATCH_SIZE + 1}/{(len(all_search_requests) + BATCH_SIZE - 1)//BATCH_SIZE}"
        logger.info(f"Processing batch {batch_id} ({len(batch)} requests)")

        # Create search tasks for this batch
        batch_tasks = []
        for request in batch:
            params = request["search_params"]
            task = single_search(
                params["query"], params["title_filter"], params["url_filter"],
                params["text_filter"], params["sites"], params["start_date"],
                params["end_date"], params["udm"], params["save_raw"],
                params["negative_url_filter"], params["negative_title_filter"])
            batch_tasks.append(task)

        # Process the batch
        batch_results = await process_batch(batch_tasks)

        # Add task metadata to results
        for j, result in enumerate(batch_results):
            if result:  # If not None or exception
                all_results.append({
                    "task_name":
                    batch[j]["task_name"],
                    "task_idx":
                    batch[j]["task_idx"],
                    "original_params":
                    batch[j]["original_params"],
                    "search_result":
                    result
                })

    return all_results


def organize_results_by_task(all_search_results):
    """Reorganize flattened search results back into task structure"""
    final_results = {"total_results_count": 0, "total_results": []}

    # Group results by task_name
    task_results = {}
    for result in all_search_results:
        task_name = result["task_name"]
        if task_name not in task_results:
            task_results[task_name] = []
        task_results[task_name].append(result)

    # Organize into final structure
    for task_name, results in task_results.items():
        # Group by task_idx which defines a query within a task
        query_results = {}
        for result in results:
            task_idx = result["task_idx"]
            if task_idx not in query_results:
                query_results[task_idx] = {
                    "query_params": result["original_params"],
                    "query_results_count": 0,
                    "query_results": []
                }

            # Add this search result to the query results
            search_result = result["search_result"]
            query_results[task_idx]["query_results"].append({
                "date_range":
                search_result["date_range"],
                "date_results_count":
                len(search_result["results"]),
                "final_query":
                search_result["final_query"],
                "date_results":
                search_result["results"]
            })
            query_results[task_idx]["query_results_count"] += len(
                search_result["results"])

        # Create task entry
        task_entry = {
            "task_name":
            task_name,
            "task_results_count":
            sum(q["query_results_count"] for q in query_results.values()),
            "task_results":
            list(query_results.values())
        }

        final_results["total_results"].append(task_entry)
        final_results["total_results_count"] += task_entry[
            "task_results_count"]

    return final_results
