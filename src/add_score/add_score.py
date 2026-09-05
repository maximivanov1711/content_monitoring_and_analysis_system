import sys
import os

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils

# Setup logger
logger = logging_utils.setup_logger("add_score.py")

# Hardcoded keywords for scoring as per requirements
AND_KEYWORDS = [
    ["арсен", "маркарян"],
    ["арсен", "маркарьян"],
    ["арсен", "макарян"],
    ["арсен", "макарьян"],
    ["arsen", "markaryan"],
    ["arsen", "markarian"],
    ["arsen", "markaran"],
]
OR_KEYWORDS = [
    "арсен",
    "маркарян",
    "arsen",
    "markaryan",
    "макарян",
    "маркарьян",
    "макарьян",
    "джага",
    "джагаспанян",
    "djaga",
]


async def calculate_score(result):
    """
    Calculate score based on keyword presence in text.

    Args:
        text (str): Text content to score

    Returns:
        int: Score (0, 1, or 2)
    """
    # Extract text content from standardized fields
    title = result.get("post_info", {}).get("title", "")
    if not title:
        title = result.get("title", "")

    text = result.get("post_info", {}).get("text", "")
    if not text:
        text = result.get("text", "")

    subtitles = result.get("subtitles_info", {}).get("subtitles", "")

    text = title + " " + text + " " + subtitles
    text = text.lower()

    if not text or len(text) == 0:
        logger.debug(
            f"Empty post text provided, returning score 1. Result url: {result.get('url')}"
        )
        return 1

    # Score = 0 if all keywords in any AND_KEYWORDS group are found
    for i, keyword_group in enumerate(AND_KEYWORDS):
        and_keywords_found = [
            keyword for keyword in keyword_group if keyword.lower() in text
        ]
        if len(and_keywords_found) == len(keyword_group):
            logger.debug(
                f"Found all keywords in AND_KEYWORDS group {i}, returning score 0. Result url: {result.get('url')}"
            )
            return 0

    # Score = 2 if at least one OR_KEYWORD is found
    or_keywords_found = [keyword for keyword in OR_KEYWORDS if keyword.lower() in text]
    if or_keywords_found:
        logger.debug(
            f"Found {or_keywords_found} OR_KEYWORDS, returning score 1. Result url: {result.get('url')}"
        )
        return 1

    # Score = 0 otherwise
    logger.debug(
        f"No keywords found, returning score 2. Result url: {result.get('url')}"
    )
    return 2


async def add_score(results):
    """
    Add score field to each result in search_results.

    Args:
        search_results (list): List of search results

    Returns:
        list: Updated search results with score fields
    """
    # Process each result
    for result in results:
        try:
            result["score"] = await calculate_score(result)

        except Exception as e:
            logging_utils.log_error(
                logger, f"Error adding score. Result url: {result.get('url')}", e
            )

            # Set default score on error
            result["score"] = 2

    return results
