from typing import Dict, Any
import sys
from datetime import datetime

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils


# Setup logger
logger = logging_utils.setup_logger(prefix="add_info_utils.py")


def should_include_post_by_date(post: Dict[str, Any], start_date: str, end_date: str) -> bool:
    """
    Check if a post should be included based on date filtering criteria.
    
    Args:
        post: The post dictionary containing post_info with date information
        start_date: Start date in YYYY-MM-DD format (optional)
        end_date: End date in YYYY-MM-DD format (optional)
    
    Returns:
        True if the post should be included, False otherwise
    """
    publication_date = post.get("post_info", {}).get("publication_date")
    
    if not publication_date:
        return True
    
    try:
        parsed_date = datetime.strptime(publication_date, "%Y-%m-%d")
    except ValueError:
        return True
    
    post_date_str = parsed_date.strftime("%Y-%m-%d")
    
    if start_date and post_date_str < start_date:
        return False
    
    if end_date and post_date_str >= end_date:
        return False
    
    return True

