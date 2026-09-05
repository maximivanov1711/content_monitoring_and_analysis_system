"""
Module for making Apify API requests to fetch raw HTML content.
"""
import sys
import os
from apify_client import ApifyClient
import dotenv

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils


# Load environment variables
dotenv.load_dotenv(dotenv_path='./.env', override=True)

# Retry up to 3 times
MAX_RETRIES = 3

# Setup logger
logger = logging_utils.setup_logger(prefix='apify_parser.py')

# Initialize the ApifyClient with your API token
client = ApifyClient(os.getenv("APIFY_API_KEY1"))


async def get_raw_html(url, wait_until="networkidle2"):
    """
    Async function to get raw HTML using Apify Web Scraper.
    
    Args:
        url (str): The URL to scrape
        wait_time (int): Number of seconds to wait for lazy-loaded content
        
    Returns:
        dict: Response in oxylabs-compatible format with HTML content
    """
    for attempt in range(MAX_RETRIES):
        try:
            # Prepare the Actor input
            run_input = {
                "breakpointLocation": "NONE",
                "browserLog": False,
                "closeCookieModals": False,
                "debugLog": False,
                "downloadCss": False,
                "downloadMedia": False,
                "headless": True,
                "ignoreCorsAndCsp": False,
                "ignoreSslErrors": False,
                "injectJQuery": False,
                "keepUrlFragments": False,
                "maxPagesPerCrawl": 3,
                "maxRequestRetries": 3,
                "maxResultsPerCrawl": 3,
                "pageFunction": "// https://apify.com/apify/web-scraper#page-function\nasync function pageFunction(context) {\n    // 1. Grab the <meta> elements with the DOM API (no jQuery)\n    const videoMeta    = document.querySelector('meta[property=\"og:video\"]');\n    const durationMeta = document.querySelector('meta[property=\"video:duration\"]');\n\n    // 2. Read their values\n    const audioUrl = videoMeta    ? videoMeta.getAttribute('content')       : null;\n    const duration = durationMeta ? Number(durationMeta.getAttribute('content')) : null;\n\n    // 3. Grab the full HTML (includes <html> tag itself)\n    const html = document.documentElement.outerHTML;\n\n    // 4. Return the result expected by Apify\n    return {\n        url:        context.request.url,\n        audio_url:  audioUrl,\n        duration,\n        html,                       // 👈 new field\n    };\n}",
                "postNavigationHooks": "// We need to return array of (possibly async) functions here.\n// The functions accept a single argument: the \"crawlingContext\" object.\n[\n    async (crawlingContext) => {\n        // ...\n    },\n]",
                "preNavigationHooks": "// We need to return array of (possibly async) functions here.\n// The functions accept two arguments: the \"crawlingContext\" object\n// and \"gotoOptions\".\n[\n    async (crawlingContext, gotoOptions) => {\n        // ...\n    },\n]\n",
                "proxyConfiguration": {
                    "useApifyProxy": True,
                    "apifyProxyGroups": [
                    "RESIDENTIAL"
                    ],
                    "apifyProxyCountry": "RU"
                },
                "proxyRotation": "PER_REQUEST",
                "respectRobotsTxtFile": True,
                "runMode": "PRODUCTION",
                "startUrls": [
                    {
                    "url": url,
                    "method": "GET"
                    }
                ],
                "useChrome": False,
                "waitUntil": [
                    wait_until
                ],
                "globs": [],
                "pseudoUrls": [],
                "excludes": [],
                "initialCookies": [],
                "maxCrawlingDepth": 0,
                "maxConcurrency": 50,
                "pageLoadTimeoutSecs": 60,
                "pageFunctionTimeoutSecs": 60,
                "maxScrollHeightPixels": 5000,
                "customData": {}
            }

            # For attempts after the first failure, use headless: false
            if attempt > 0:
                run_input["headless"] = False
            
            # Run the Actor and wait for it to finish
            run = client.actor("moJRLRc85AitArpNN").call(run_input=run_input, timeout_secs=9999)
            
            if not run or "defaultDatasetId" not in run:
                logging_utils.log_warning(logger, f"No valid run result from Apify for URL: {url}, retrying for {attempt + 1}/{MAX_RETRIES} times")
                continue
                
            # Fetch results from the run's dataset
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            
            # Get the HTML content from the first (and only) result
            html_content = items[0].get('html')

            if not html_content:
                logging_utils.log_warning(logger, f"No HTML returned from Apify for URL: {url}, retrying for {attempt + 1}/{MAX_RETRIES} times")
                continue

            if "ERR_EMPTY_RESPONSE" in html_content:
                logging_utils.log_warning(logger, f"ERR_EMPTY_RESPONSE returned from Apify for URL: {url}, retrying for {attempt + 1}/{MAX_RETRIES} times")
                continue

            # Check if HTML contains CheckboxCaptcha
            if "CheckboxCaptcha" in html_content:
                logging_utils.log_warning(logger, f"CheckboxCaptcha detected in HTML for URL: {url}, retrying for {attempt + 1}/{MAX_RETRIES} times")
                continue
            
            # Return in oxylabs-compatible format
            return html_content
 
        except Exception as e:
            logging_utils.log_error(logger, f"Error in 'apify_parser.get_raw_html()'. 'url': {url}, attempt {attempt + 1}/{MAX_RETRIES}", e)
            continue
    
    logging_utils.log_error(logger, f"Max retries reached in 'apify_parser.get_raw_html()'. 'url': {url}")
    return None