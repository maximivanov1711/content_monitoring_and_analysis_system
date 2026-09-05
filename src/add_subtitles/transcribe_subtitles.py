import aiohttp
import os
import json
import asyncio
import dotenv
import sys

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import utils
from src.add_subtitles import download_media
from src.utils import logging_utils

# Setup logger
logger = logging_utils.setup_logger("transcribe_subtitles.py")

# Load environment variables
dotenv.load_dotenv()

# Set constants
SALAD_API_KEY = os.environ.get("SALAD_API_KEY")


async def transcribe_subtitles(result, task={}):
    # Extract transcribe parameter from task if available
    transcribe = task.get("add_subtitles_parameters", {}).get("transcribe", True)
    force_download_media = task.get("add_subtitles_parameters", {}).get("force_download_media", False)
    max_duration = task.get("add_subtitles_parameters", {}).get("max_duration", 0)

    if len(result.get("subtitles_info", {}).get("media", [])) == 0 or force_download_media:
        media_info = await download_media.download_media(result, task)
        if media_info is not None:
            result["subtitles_info"] = {
                **result.get("subtitles_info", {}),
                **media_info
            }
        else:
            result["subtitles_info"] = result.get("subtitles_info", {})

    if not transcribe:
        return result

    if len(result["subtitles_info"].get("media", [])) == 0:
        return result

    if result["subtitles_info"].get("duration", 0) >= max_duration:
        return result

    transcribe_url = "https://api.salad.com/api/public/organizations/bestai/inference-endpoints/transcribe/jobs"
    headers = {
        "Content-Type": "application/json",
        "Salad-Api-Key": SALAD_API_KEY
    }
    
    # Try with sentence_level_timestamps first, then without if it fails
    async with aiohttp.ClientSession() as session:
        for attempt in range(3):
            include_timestamps = attempt == 0  # First attempt with timestamps, second without
            
            # Check if media URL is available
            media_url = result["subtitles_info"]["media"][0]
            
            payload = {
                "input": {
                    "url": media_url,
                    "return_as_file": True
                }
            }
            
            if include_timestamps:
                payload["input"]["sentence_level_timestamps"] = True
            
            try:
                async with session.post(transcribe_url, headers=headers, json=payload) as response:
                    response.raise_for_status()

                    response_data = await response.json()
                    job_url = f"https://api.salad.com/api/public/organizations/bestai/inference-endpoints/transcribe/jobs/{response_data['id']}"
            except Exception as e:
                logging_utils.log_error(logger, f"Failed to create transcription job on attempt {attempt + 1}: {e}", e)
                if attempt == 1:  # Last attempt
                    return result
                continue

            poll_count = 0
            job_failed = False
            while True:
                await asyncio.sleep(5)
                poll_count += 1

                try:
                    async with session.get(job_url, headers=headers) as result_response:
                        result_response.raise_for_status()

                        job_result = await result_response.json()
                        status = job_result["status"]

                        if status == "succeeded" and "output" in job_result:
                            # Download the result file
                            file_url = job_result["output"]["url"]
                            
                            async with session.get(file_url) as file_response:
                                file_response.raise_for_status()
                                transcription_data = await file_response.json()
                            
                            result["subtitles_info"]["subtitles"] = utils.format_transcript(transcription_data)
                            return result
                        elif status == "failed":
                            logging_utils.log_error(logger, f"Transcription job failed. Result url: {result['url']}, 'job_result': {json.dumps(job_result, indent=4, ensure_ascii=False)}")
                            job_failed = True
                            break
                        elif poll_count > result["subtitles_info"].get("duration", 1000):  # Stop after duration seconds
                            logging_utils.log_error(logger, f"Transcription job timed out after {poll_count} polling attempts. Result url: {result['url']}")
                            job_failed = True
                            break
                except Exception as e:
                    logging_utils.log_error(logger, f"Error polling transcription job. Result url: {result['url']}, 'job_result': {json.dumps(job_result, indent=4, ensure_ascii=False)}", e)
                    job_failed = True
                    break           

            # If job failed and this was the first attempt, try again without timestamps
            if job_failed and attempt == 0:
                logging_utils.log_warning(logger, f"First transcription attempt failed, retrying without sentence_level_timestamps. Result url: {result['url']}")
                continue
            elif job_failed:
                logging_utils.log_error(logger, f"Transcription attempt failed, retrying. Attempt {attempt + 1}/{3}, result url: {result['url']}")
                break

    return result