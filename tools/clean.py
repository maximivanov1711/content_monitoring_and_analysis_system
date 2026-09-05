import json5 
import copy
import os
import sys
import shutil
import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

from utils import logging_utils
from src.utils.utils import is_excluded_profile

logger = logging_utils.setup_logger(prefix='cleaner.py')

def normalize_link(url: str) -> str:
    """
    Normalize URLs by stripping off query‐strings except for special cases.
    """

    # preserve these exact patterns
    if "/fv?to" in url or "youtube.com/watch?v=" in url:
        return url

    url = url.split("?")[0]

    url = url.replace("https://m.vk.com", "https://vk.com")

    if "twitch.tv" in url:
        if "clips.twitch.tv" in url:
            return url
            # # Extract the clip ID as the last part of the URL path
            # parts = url.rstrip('/').split('/')
            # clip_id = parts[-1]
            # # You can use clip_id as needed, e.g., for further normalization or logging
            # return clip_id
        if "/clip/" in url:
            clip_id = url.split("/clip/")[1]
            return f"https://clips.twitch.tv/{clip_id}"
        
        if "/videos/" in url:
            video_id = url.split("/videos/")[1]
            return f"https://www.twitch.tv/videos/{video_id}"
    
        return None

    return url

def normalize_links(search_results: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    First pass: drop any result whose URL normalization fails (returns None).
    Returns (cleaned_results, deleted_results) where deleted_results
    has the same nested structure but only those 'bad_url' items.
    """
    cleaned_results = search_results.copy()
    deleted_results = {k: v for k, v in search_results.items() if k != "total_results"}
    deleted_results["total_results_count"] = 0
    deleted_results["total_results"] = []

    for task in cleaned_results["total_results"]:
        deleted_task = task.copy()
        deleted_task["task_results"] = []
        deleted_task["task_results_count"] = 0

        for query in task["task_results"]:
            deleted_query = query.copy()
            deleted_query["query_results"] = []
            deleted_query["query_results_count"] = 0

            for date_range in query["query_results"]:
                new_date_results = []
                deleted_date_range = date_range.copy()
                deleted_date_range["date_results"] = []
                deleted_date_range["date_results_count"] = 0

                for result in date_range["date_results"]:
                    url = result["url"] if "url" in result else ""
                    normalized = normalize_link(url)
                    if normalized is None:
                        deleted_date_range["date_results"].append(result.copy())
                    elif "youtube.com/watch?v=" in normalized:
                        if "type" in result and result["type"] != "video":
                            deleted_date_range["date_results"].append(result.copy())
                        else:
                            result["url"] = normalized
                            new_date_results.append(result)
                    else:
                        result["url"] = normalized
                        new_date_results.append(result)

                date_range["date_results"] = new_date_results
                date_range["date_results_count"] = len(new_date_results)

                deleted_date_range["date_results_count"] = len(deleted_date_range["date_results"])
                if deleted_date_range["date_results"]:
                    deleted_query["query_results"].append(deleted_date_range)

            query["query_results_count"] = sum(dr["date_results_count"]
                                              for dr in query["query_results"])
            deleted_query["query_results_count"] = sum(dr["date_results_count"]
                                                      for dr in deleted_query["query_results"])
            if deleted_query["query_results"]:
                deleted_task["task_results"].append(deleted_query)

        task["task_results_count"] = sum(q["query_results_count"]
                                        for q in task["task_results"])
        deleted_task["task_results_count"] = sum(q["query_results_count"]
                                                for q in deleted_task["task_results"])
        if deleted_task["task_results"]:
            deleted_results["total_results"].append(deleted_task)

    deleted_results["total_results_count"] = sum(t["task_results_count"]
                                                for t in deleted_results["total_results"])
    cleaned_results["total_results_count"] = sum(t["task_results_count"]
                                                for t in cleaned_results["total_results"])

    return cleaned_results, deleted_results

def remove_duplicated_urls(search_results: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Remove duplicate search results from the search results object.
    
    Args:
        search_results: The original search results
        
    Returns:
        Tuple of (clean results with duplicates removed, deleted duplicates)
    """
    seen_urls = set()
    
    cleaned_results = search_results.copy()
    deleted_results = {k: v for k, v in search_results.items() if k != "total_results"}
    deleted_results["total_results_count"] = 0
    deleted_results["total_results"] = []

    for task_idx, task in enumerate(cleaned_results["total_results"]):
        # Create a copy of the task for deleted items, but with empty results
        deleted_task = task.copy()
        deleted_task["task_results"] = []
        deleted_task["task_results_count"] = 0
        
        for query_idx, query in enumerate(task["task_results"]):
            # Create a copy of the query for deleted items, but with empty results
            deleted_query = query.copy()
            deleted_query["query_results"] = []
            deleted_query["query_results_count"] = 0
            
            for date_idx, date_range in enumerate(query["query_results"]):
                unique_results = []
                # Create a copy of the date_range for deleted items, but with empty results
                deleted_date_range = date_range.copy()
                deleted_date_range["date_results"] = []
                deleted_date_range["date_results_count"] = 0
                
                for result in date_range["date_results"]:
                    url = result["url"]

                    if url not in seen_urls:
                        seen_urls.add(url)
                        unique_results.append(result)
                    else:
                        deleted_date_range["date_results"].append(result)
                
                date_range["date_results"] = unique_results
                date_range["date_results_count"] = len(unique_results)
                
                deleted_date_range["date_results_count"] = len(deleted_date_range["date_results"])
                if deleted_date_range["date_results"]:
                    deleted_query["query_results"].append(deleted_date_range)
            
            query["query_results_count"] = sum(date_range["date_results_count"]
                                              for date_range in query["query_results"])
            
            deleted_query["query_results_count"] = sum(date_range["date_results_count"]
                                                     for date_range in deleted_query["query_results"])
            if deleted_query["query_results"]:
                deleted_task["task_results"].append(deleted_query)
        
        task["task_results_count"] = sum(query["query_results_count"]
                                        for query in task["task_results"])
        
        deleted_task["task_results_count"] = sum(query["query_results_count"]
                                               for query in deleted_task["task_results"])
        if deleted_task["task_results"]:
            deleted_results["total_results"].append(deleted_task)
    
    cleaned_results["total_results_count"] = sum(task["task_results_count"]
                                               for task in cleaned_results["total_results"])
    
    deleted_results["total_results_count"] = sum(task["task_results_count"]
                                               for task in deleted_results["total_results"])
    
    return cleaned_results, deleted_results

def remove_excluded_profiles(search_results: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Remove search results from excluded profiles from the cleaned results,
    and collect them in the deleted results structure.
    """
    cleaned_results = search_results.copy()
    deleted_results = {k: v for k, v in search_results.items() if k != "total_results"}
    deleted_results["total_results_count"] = 0
    deleted_results["total_results"] = []

    for task_idx, task in enumerate(cleaned_results["total_results"]):
        deleted_task = task.copy()
        deleted_task["task_results"] = []
        deleted_task["task_results_count"] = 0

        for query_idx, query in enumerate(task["task_results"]):
            deleted_query = query.copy()
            deleted_query["query_results"] = []
            deleted_query["query_results_count"] = 0

            for date_idx, date_range in enumerate(query["query_results"]):
                deleted_date_range = date_range.copy()
                deleted_date_range["date_results"] = []
                deleted_date_range["date_results_count"] = 0

                # Only keep non-excluded results in cleaned results
                new_date_results = []
                for result in date_range["date_results"]:
                    url = result["url"]
                    if "profile_url" in result:
                        profile_url = result["profile_url"]
                        is_excluded = utils.is_excluded_profile(url) or utils.is_excluded_profile(profile_url)
                    else:
                        is_excluded = utils.is_excluded_profile(url)
                    if is_excluded:
                        deleted_date_range["date_results"].append(result.copy())
                    else:
                        new_date_results.append(result)

                date_range["date_results"] = new_date_results
                date_range["date_results_count"] = len(new_date_results)

                deleted_date_range["date_results_count"] = len(deleted_date_range["date_results"])
                if deleted_date_range["date_results"]:
                    deleted_query["query_results"].append(deleted_date_range)

            query["query_results_count"] = sum(date_range["date_results_count"]
                                              for date_range in query["query_results"])

            deleted_query["query_results_count"] = sum(date_range["date_results_count"]
                                                     for date_range in deleted_query["query_results"])
            if deleted_query["query_results"]:
                deleted_task["task_results"].append(deleted_query)

        task["task_results_count"] = sum(query["query_results_count"]
                                        for query in task["task_results"])

        deleted_task["task_results_count"] = sum(query["query_results_count"]
                                               for query in deleted_task["task_results"])
        if deleted_task["task_results"]:
            deleted_results["total_results"].append(deleted_task)

    deleted_results["total_results_count"] = sum(task["task_results_count"]
                                               for task in deleted_results["total_results"])
    
    cleaned_results["total_results_count"] = sum(task["task_results_count"]
                                               for task in cleaned_results["total_results"])

    return cleaned_results, deleted_results

def setup_output_directories():
    """
    Create cleaned_results and cleaned_results/previous directories if they don't exist.
    Move existing files from cleaned_results to cleaned_results/previous.
    """
    os.makedirs("search_results_cleaned/previous", exist_ok=True)
    
    for file in os.listdir("search_results_cleaned"):
        file_path = os.path.join("search_results_cleaned", file)
        if os.path.isfile(file_path) and file != ".gitkeep":
            shutil.move(file_path, os.path.join("search_results_cleaned/previous", file))

def generate_timestamp_filename(input_filename):
    """
    Generate a filename with the current timestamp in the format:
    filename_cleaned_YYYY_MM_DD_HH_mm_SS.json
    
    Args:
        input_filename: Original filename to prepend
        
    Returns:
        A filename string with the original name and current timestamp
    """
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y_%m_%d_%H_%M_%S")
    
    # Extract base filename without path and extension
    base_filename = os.path.basename(input_filename)
    base_filename = os.path.splitext(base_filename)[0]
    
    filename = f"{base_filename}_cleaned_{timestamp}.json"
    return filename

def clean_search_results(input_files: List[str]) -> None:
    """
    Main function to clean search results by applying all cleaning steps.
    Processes each input file separately and creates individual output files
    in the cleaned_results folder.
    
    Args:
        input_files: List of paths to input JSON files with search results
    """
    setup_output_directories()
    
    for input_file in input_files:
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                search_results = json5.load(f)
            
            # Check if file has the expected structure
            if "total_results" not in search_results:
                logging_utils.log_warning(logger, f"Skipping {input_file}: Missing 'total_results' key in file structure")
                continue
                
            # Stage 1: normalize links, collect any with None → bad_url
            normalized_results, deleted_bad_urls = normalize_links(search_results)
            # Stage 2: remove duplicates
            cleaned_results, deleted_duplicates = remove_duplicated_urls(normalized_results)
            # Stage 3: remove excluded profiles
            final_results, deleted_excluded_profiles = remove_excluded_profiles(cleaned_results)
            
            # Filter out date ranges with zero results
            for task in final_results["total_results"]:
                for query in task["task_results"]:
                    query["query_results"] = [date_range for date_range in query["query_results"] 
                                              if date_range["date_results_count"] > 0]
            
            # Recalculate counts after filtering out empty date ranges
            for task in final_results["total_results"]:
                for query in task["task_results"]:
                    query["query_results_count"] = sum(date_range["date_results_count"] 
                                                     for date_range in query["query_results"])
                task["task_results_count"] = sum(query["query_results_count"] 
                                               for query in task["task_results"])
            final_results["total_results_count"] = sum(task["task_results_count"] 
                                                     for task in final_results["total_results"])
            
            # Structure output with separate deleted results for each cleaning function
            output_structure = {
                "search_results_cleaned": final_results,
                "bad_urls": deleted_bad_urls,
                "duplicated_urls": deleted_duplicates,
                "excluded_profiles": deleted_excluded_profiles
            }
            
            # enerate output filename with timestamp based on input filename
            output_filename = generate_timestamp_filename(input_file)
            output_file = os.path.join("search_results_cleaned", output_filename)
            
            # Save the output
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_structure, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Processed {input_file} and saved to {output_file}")
        except Exception as e:
            logger.error(f"Error processing {input_file}: {str(e)}")

if __name__ == "__main__":
    clean_search_results(
        [
            "tg/search_telegram_result_new.json"
        ]
    )