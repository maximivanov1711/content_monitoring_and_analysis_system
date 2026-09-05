import sys
import asyncio

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils
from src.analyze import analyze_utils
from src.analyze import llm


# Setup logger
logger = logging_utils.setup_logger('analyze.py')


async def analyze(results, task={}):
    """
    Analyze search results for sentiment and extract negative moments using async OpenAI API calls.
    
    Args:
        results: List of search result dictionaries
        task: Dictionary containing processing parameters
    
    Returns:
        List of search results enhanced with analysis information
    """
    try:
        # Sort results for analysis
        results = analyze_utils.sort_results(results)
        
        # Filter results by score if score_filter is provided
        score_filter = task.get("analyze_parameters", {}).get("score_filter")
        
        if score_filter:
            results_for_analysis = [r for r in results if r.get('score') in score_filter]
            results_filtered_out = [r for r in results if r.get('score') not in score_filter]
        else:
            results_for_analysis = results
            results_filtered_out = []

        logger.info(f"Filtered results by score. Score filter: {score_filter}. Number of results for analysis: {len(results_for_analysis)}. Number of results filtered out: {len(results_filtered_out)}")
        
        # Filter results by post type if post_types is provided
        post_types = task.get("analyze_parameters", {}).get("post_types")
        results_for_analysis = [r for r in results_for_analysis if not post_types or r.get('post_type') in post_types]
        logger.info(f"Filtered results by post type. Post types: {post_types}. Number of results after filtering: {len(results_for_analysis)}")
        
        # Execute all tasks concurrently with staggered start times
        analysis_tasks = [llm.analyze_result(result, i, task) for i, result in enumerate(results_for_analysis)]
        analyzed_results = await asyncio.gather(*analysis_tasks)
        
        results = analyzed_results + results_filtered_out

    except Exception as e:
        logging_utils.log_error(logger, f"Error in analyze.analyze()", e)
    
    return results