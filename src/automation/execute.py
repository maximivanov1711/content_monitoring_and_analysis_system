import sys

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils
from src.utils import utils
from src.search import search
from src.add_info import add_info
from src.add_subtitles import add_subtitles
from src.analyze import analyze
import src.export.export as export
from src.storage import local_storage


# Setup logger
logger = logging_utils.setup_logger("execute.py")

# Load excluded profiles and editor profiles
utils.load_excluded_profiles()
utils.load_editor_profiles()


async def execute(task={}):
    """
    Execute a task according to its parameters with comprehensive error handling.
    
    Args:
        task (dict): Raw task configuration containing search parameters, add info parameters,
                     add subtitles parameters, and analyze parameters
    """
    logger.info(f"Starting execute.py")

    # Search for content
    search_results = await search.search(task)
    
    # Add info to search results
    if task.get("add_info_parameters", {}).get("enabled", False):
        search_results = await add_info.add_info(search_results, task)
    
    # Add subtitles to high-scoring results
    if task.get("add_subtitles_parameters", {}).get("enabled", False):
        search_results = await add_subtitles.add_subtitles(search_results, task)
    
    # Analyze content for sentiment and moments
    if task.get("analyze_parameters", {}).get("enabled", False):
        search_results = await analyze.analyze(search_results, task)
    
    # Export final results
    if task.get("export_parameters", {}).get("enabled", False):
        await export.export(search_results, task)
    
    # Save final results locally
    if task.get("storage_parameters", {}).get("save_final_results", True):
        local_storage.save_results_locally(search_results, "final_results")
    
    logger.info(f"Finished execute.py")
    return search_results
