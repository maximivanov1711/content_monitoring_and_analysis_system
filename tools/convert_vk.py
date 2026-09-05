import json5 
import os
import asyncio
import logging
from datetime import datetime
from processors.vk import get_vk_profile_info
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Batch processing settings
BATCH_SIZE = 40
delay_between_batches = 0.1
delay_between_calls = 0.1

async def process_vk_videos(input_file_path):
    # Read input JSON file
    with open(input_file_path, 'r', encoding='utf-8') as f:
        data = json5.load(f)
    
    logger.info(f"Processing {len(data)} videos from {input_file_path}")
    
    # Create output filename based on input filename and current date
    input_basename = os.path.splitext(os.path.basename(input_file_path))[0]
    current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{input_basename}_{current_date}.json"
    
    # Create output directory if it doesn't exist
    os.makedirs("vk_videos", exist_ok=True)
    output_file_path = os.path.join("vk_videos", output_filename)
    
    # Initialize output structure with empty results
    results = []
    total_count = len(data)
    output = {
        "search_results_cleaned": {
            "total_results_count": total_count,
            "total_results": [
                {
                    "task_name": "seatch_vk_videos",
                    "task_results_count": total_count,
                    "task_results": [
                        {
                            "query_params": {
                                "query": "all"
                            },
                            "query_results_count": total_count,
                            "query_results": [
                                {
                                    "date_range": "all",
                                    "date_results_count": total_count,
                                    "date_results": results
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }
    
    # Create initial output file
    with open(output_file_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"Created initial output file: {output_file_path}")
    
    # Calculate number of batches
    total_batches = (len(data) + BATCH_SIZE - 1) // BATCH_SIZE
    logger.info(f"Processing videos in {total_batches} batches of {BATCH_SIZE}")
    
    save_counter = 0
    
    # Process in batches
    for batch_idx in range(total_batches):
        batch_start = batch_idx * BATCH_SIZE
        batch_end = min(batch_start + BATCH_SIZE, len(data))
        current_batch = data[batch_start:batch_end]
        
        logger.info(f"Processing batch {batch_idx + 1}/{total_batches} (items {batch_start+1}-{batch_end})")
        
        # Create concurrent tasks for the batch
        tasks = []
        for i, item in enumerate(current_batch):
            # Calculate delay for staggered start
            delay = i * delay_between_calls
            tasks.append(asyncio.create_task(process_video_item(item, delay, i + batch_start)))
        
        # Wait for all tasks in the batch to complete
        batch_results = await asyncio.gather(*tasks)
        
        # Add results to the main results list
        results.extend(batch_results)
        save_counter += len(batch_results)
        
        # Update results in the output structure
        output["search_results_cleaned"]["total_results"][0]["task_results"][0]["query_results"][0]["date_results"] = results
        
        # Save after every 10 items or at the end
        if save_counter >= 10 or batch_idx == total_batches - 1:
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            logger.info(f"Updated output file after processing {len(results)}/{len(data)} videos")
            save_counter = 0
        
        # Wait between batches if not the last batch
        if batch_idx < total_batches - 1:
            logger.info(f"Waiting {delay_between_batches}s before next batch...")
            await asyncio.sleep(delay_between_batches)
    
    logger.info(f"Processing complete. Output saved to: {output_file_path}")
    return output_file_path

async def process_video_item(item, delay, item_index):
    # Apply the delay for staggered start
    await asyncio.sleep(delay)
    
    logger.info(f"Processing video {item_index + 1}")
    
    # Extract subtitles links if available
    subtitles_links = []
    if item.get("has_subtitles") and "subtitles" in item and item["subtitles"]:
        for subtitle in item["subtitles"]:
            if "url" in subtitle:
                subtitles_links.append(subtitle["url"])
    
    # Create post_info field
    post_info = {
        "comments_count": item.get("comments"),
        "publication_date": datetime.fromtimestamp(item.get("date")).strftime("%Y-%m-%d") if item.get("date") else None,
        "description": item.get("description"),
        "duration": item.get("duration"),
        "has_subtitles": item.get("has_subtitles"),
        "likes_count": item.get("likes", {}).get("count"),
        "owner_id": item.get("owner_id"),
        "reposts_count": item.get("reposts", {}).get("count"),
        "subtitles_links": subtitles_links,
        "title": item.get("title"),
        "type": item.get("type"),
        "url": item.get("url"),
        "views_count": item.get("views")
    }
    
    # Create profile URL from owner_id
    owner_id = item.get("owner_id")
    if owner_id:
        if owner_id < 0:  # Group/community
            profile_url = f"https://vk.com/club{abs(owner_id)}?w=club{abs(owner_id)}"
        else:  # User
            profile_url = f"https://vk.com/id{owner_id}"
        
        # Get profile info
        profile_info_content = {
            "profile_url": profile_url
        }
        logger.info(f"Fetching profile info for owner_id: {owner_id}, URL: {profile_url}")
        enhanced_content = await get_vk_profile_info(profile_info_content)
        post_info["profile_info"] = enhanced_content.get("profile_info", {})
        logger.info(f"Retrieved profile info: {post_info['profile_info']}")
    
    # Add post_info to the item
    item_with_post_info = dict(item)
    item_with_post_info["post_info"] = post_info
    
    return item_with_post_info

def sync_process_vk_videos(input_file_path):
    logger.info(f"Starting VK videos processing")
    result = asyncio.run(process_vk_videos(input_file_path))
    logger.info(f"VK videos processing completed")
    return result

if __name__ == "__main__":
    # Assuming the input file is in the current directory
    input_path = "search_results_ideal/search_vk_videos_ideal.json"  # Update this path if needed
    output_path = sync_process_vk_videos(input_path)
    print(f"Processed data saved to: {output_path}")
