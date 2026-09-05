import sys
import os
import asyncio
from typing import List, Dict
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
import dotenv

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.storage import db
from src.utils import logging_utils
from src.analyze import analyze_utils


# Load environment variables
dotenv.load_dotenv(override=True)

# Setup logger
logger = logging_utils.setup_logger('llm.py')

# Delay between each request
REQUEST_DELAY = 2

# Chunk size for long content
CHUNK_SIZE = 1000

# Initialize OpenAI client
llm_client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)


class AnalysisResult(BaseModel):
    """Structured response format for content analysis."""
    negative_moments: List[str] = Field(
        description="List of negative quotes from the content. For subtitles, include timestamp in format 'HH:MM:SS - quote'"
    )


async def make_analysis_api_call(system_prompt: str, user_prompt: str):
    """
    Make a single API call to OpenAI for content analysis.
    
    Args:
        system_prompt: The system prompt for the API call
        user_prompt: The user prompt for the API call
        
    Returns:
        The API response object
    """
    response = await llm_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format=AnalysisResult,
        temperature=0.1
    )
    return response


async def analyze_result(result: Dict, index: int, task: Dict) -> Dict:
    """
    Analyze a single result using OpenAI API.
    
    Args:
        result: Single result dictionary
        task: Task parameters
        
    Returns:
        Result dictionary with analysis data
    """
    try:
        # Add delay before starting each request
        await asyncio.sleep(index * REQUEST_DELAY)

        # Extract parameters from task
        analyze_parameters = task.get("analyze_parameters", {})
        use_cache = analyze_parameters.get("use_cache", True)
        update_cache = analyze_parameters.get("update_cache", True)
        fields_to_update = analyze_parameters.get("fields_to_update", None)

        # Check cache first if enabled
        if use_cache:
            cached_post_info = await db.get_post(result['url'])
            if cached_post_info and cached_post_info.get('analysis_info', {}).get('negative_moments'):
                logger.debug(f"Analysis data cache hit. Result url: {result['url']}")
                result['analysis_info'] = cached_post_info['analysis_info']
                return result

        # Get text and subtitles content for length checking
        text_content = result.get('post_info', {}).get('text', '')
        subtitles_content = result.get('subtitles_info', {}).get('subtitles', '')
        
        # Count words in text and subtitles
        text_word_count = len(text_content.split()) if text_content else 0
        subtitles_word_count = len(subtitles_content.split()) if subtitles_content else 0
        
        # Determine processing strategy based on content length
        if text_word_count > CHUNK_SIZE:
            # Process text only (without subtitles) in chunks
            logger.debug(f"Text exceeds {CHUNK_SIZE} words, processing text only in chunks. Result url: {result['url']}")
            final_text = analyze_utils.build_final_text_text_only(result)
            process_subtitles = False
        elif subtitles_word_count > CHUNK_SIZE:
            # Process subtitles only (without text) in chunks
            logger.debug(f"Subtitles exceed {CHUNK_SIZE} words, processing subtitles only in chunks. Result url: {result['url']}")
            final_text = analyze_utils.build_final_text_subtitles_only(result)
            process_subtitles = True
        else:
            # Process both text and subtitles together
            logger.debug(f"Both text and subtitles are under {CHUNK_SIZE} words, processing together. Result url: {result['url']}")
            final_text = analyze_utils.build_final_text(result)
            process_subtitles = bool(subtitles_content)

        result['analysis_info']['final_text'] = final_text

        if not final_text:
            logger.warning(f"No final_text found for analysis. Result url: {result['url']}")
            return result

        # Select appropriate prompts based on content type
        if process_subtitles:
            system_prompt_path = task.get('analyze_parameters', {}).get('subtitles_system_prompt_path')
            user_prompt_path = task.get('analyze_parameters', {}).get('subtitles_user_prompt_path')  
        else:
            system_prompt_path = task.get('analyze_parameters', {}).get('text_system_prompt_path')
            user_prompt_path = task.get('analyze_parameters', {}).get('text_user_prompt_path')

        # Load prompts
        system_prompt = analyze_utils.load_analysis_prompt(system_prompt_path)
        user_prompt_template = analyze_utils.load_analysis_prompt(user_prompt_path)
        
        # Handle text chunking for long content
        words = final_text.split()
        
        all_negative_moments = []
        all_raw_responses = []
        
        # Create list of user prompts to process
        if len(words) > CHUNK_SIZE:
            # Process in chunks of the complete final_text
            logger.debug(f"Analyzing results in {len(range(0, len(words), CHUNK_SIZE))} chunks. Result url: {result['url']}")
            
            user_prompts = []
            for chunk_start in range(0, len(words), CHUNK_SIZE):
                chunk_words = words[chunk_start:chunk_start + CHUNK_SIZE]
                chunk_final_text = ' '.join(chunk_words)
                chunk_user_prompt = user_prompt_template.format(final_text=chunk_final_text)
                user_prompts.append(chunk_user_prompt)
        else:
            # Single request for normal content
            user_prompt = user_prompt_template.format(final_text=final_text)
            user_prompts = [user_prompt]
        
        # Process all prompts
        for i, user_prompt in enumerate(user_prompts):
            response = await make_analysis_api_call(system_prompt, user_prompt)
            negative_moments = response.choices[0].message.parsed.negative_moments
            all_negative_moments.extend(negative_moments)
            all_raw_responses.append(response.to_json())
            
            if len(user_prompts) > 1:
                logger.debug(f"Finished analyzing chunk {i+1}. Result url: {result['url']}")
        
        result['analysis_info'].update({
            'negative_moments': all_negative_moments,
            'raw_analysis_response': all_raw_responses,
            'sentiment': "DANGEROUS" if all_negative_moments else "SAFE"
        })
        
        # Update cache if we have new data and cache update is enabled
        if update_cache:
            await db.save_post(result['url'], result, fields_to_update=fields_to_update)
        
    except Exception as e:
        error_info = logging_utils.log_error(logger, f"Error analyzing result. Result url: {result['url']}", e)
        result['debug_info']['errors'].append(error_info)
    
    return result
