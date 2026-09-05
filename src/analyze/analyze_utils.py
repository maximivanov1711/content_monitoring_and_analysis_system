import sys
from datetime import datetime

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils

# Setup logger
logger = logging_utils.setup_logger('analyze_utils.py')


def should_analyze(result):
    """
    Determines if a post should be analyzed based on views and publication date.
    
    Args:
        result: Dictionary containing post_info with publication_date and views_count
        
    Returns:
        bool: True if post should be analyzed, False otherwise
    """
    try:
        publication_date = result.get("post_info",
                                      {}).get("publication_date", "")
        views_count = result.get("post_info", {}).get("views_count", 0)
        if isinstance(views_count, str):
            views_count = 0

        # Check for relative date indicator - always analyze these posts
        if "относительно" in publication_date:
            reason = "relative publication date ('относительно')"
            decision = True
            logger.debug(
                f"Returning should_analyse = {decision}. Reason: {reason}. Result url: {result['url']}."
            )
            return decision

        # Parse publication date and calculate days passed
        pub_date = datetime.strptime(publication_date, "%Y-%m-%d")
        days_passed = (datetime.now() - pub_date).days

        # Check if views exceed threshold (100 views per day, or 300 if score is not 0)
        multiplier = 300 if result.get("score", 0) != 0 else 100
        threshold = days_passed * multiplier
        if views_count > threshold:
            reason = f"views ({views_count}) exceed threshold ({threshold})"
            decision = True
        else:
            reason = f"views ({views_count}) do not exceed threshold ({threshold})"
            decision = False

    except Exception as e:
        # Handle invalid date formats or missing data
        reason = f"error - {e}"
        decision = False

    logger.debug(
        f"Returning should_analyse = {decision}. Reason: {reason}. Result url: {result['url']}."
    )
    return decision


def sort_results(results):
    """
    Sorts results by multiple criteria:
    1. By result.score (descending)
    2. For same score, by result.post_info.publication_date (descending)
    3. For same score and date, by result.post_info.views_count (descending)
    4. Results with "относительно" in date come last within their date group
    
    Args:
        results: List of result dictionaries
        
    Returns:
        List: Sorted results
    """

    def sort_key(result):
        score = result.get("score", 2)
        publication_date = result.get("post_info",
                                      {}).get("publication_date", "")
        views_count = result.get("post_info", {}).get("views_count", 0)
        if isinstance(views_count, str):
            views_count = 0

        # Handle relative dates - they should come last in their date group
        has_relative_date = "относительно" in publication_date

        # For date sorting, try to parse actual date, fallback to string comparison
        try:
            if not has_relative_date:
                parsed_date = datetime.strptime(publication_date, "%Y-%m-%d")
            else:
                # For relative dates, use a very old date so they sort last
                parsed_date = datetime(1970, 1, 1)
        except:
            parsed_date = datetime(1970, 1, 1)

        # Return tuple for sorting (negative values for descending order)
        return (
            -score,  # Higher scores first
            -parsed_date.timestamp(),  # Newer dates first
            has_relative_date,  # False (non-relative) comes before True (relative)
            -(views_count or 0)  # Higher views first
        )

    return sorted(results, key=sort_key)


def load_analysis_prompt(prompt_path):
    """
    Load analysis prompt from markdown file.
    
    Args:
        prompt_path: Path to the prompt markdown file
        
    Returns:
        str: The loaded prompt content
    """
    with open(prompt_path, 'r', encoding='utf-8') as file:
        return file.read()


def build_final_text(result):
    """
    Build the final text from title, description, and subtitles.
    
    Args:
        result: Dictionary containing the result data
        
    Returns:
        str: The formatted final text
    """
    final_text_parts = []

    # Add title if it exists and is not empty
    title = result.get('post_info', {}).get('title', '')
    if title:
        final_text_parts.append(f"Title:\n{title}")

    # Add description if it exists and is not empty
    description = result.get('post_info', {}).get('text', '')
    if description:
        final_text_parts.append(f"Description:\n{description}")

    # Add subtitles if they exist and are not empty
    subtitles = result.get('subtitles_info', {}).get('subtitles', '')
    if subtitles:
        final_text_parts.append(f"Subtitles:\n{subtitles}")

    return '\n\n'.join(final_text_parts)


def build_final_text_text_only(result):
    """
    Build the final text from title and description only (excluding subtitles).
    
    Args:
        result: Dictionary containing the result data
        
    Returns:
        str: The formatted final text without subtitles
    """
    final_text_parts = []

    # Add title if it exists and is not empty
    title = result.get('post_info', {}).get('title', '')
    if title:
        final_text_parts.append(f"Title:\n{title}")

    # Add description if it exists and is not empty
    description = result.get('post_info', {}).get('text', '')
    if description:
        final_text_parts.append(f"Description:\n{description}")

    return '\n\n'.join(final_text_parts)


def build_final_text_subtitles_only(result):
    """
    Build the final text from title and subtitles only (excluding description/text).
    
    Args:
        result: Dictionary containing the result data
        
    Returns:
        str: The formatted final text without description/text
    """
    final_text_parts = []

    # Add title if it exists and is not empty
    title = result.get('post_info', {}).get('title', '')
    if title:
        final_text_parts.append(f"Title:\n{title}")

    # Add subtitles if they exist and are not empty
    subtitles = result.get('subtitles_info', {}).get('subtitles', '')
    if subtitles:
        final_text_parts.append(f"Subtitles:\n{subtitles}")

    return '\n\n'.join(final_text_parts)
