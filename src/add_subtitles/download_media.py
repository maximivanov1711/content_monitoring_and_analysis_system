import json
import base64
import apify_client
import os
import dotenv
import tempfile
import ffmpeg
import sys
import asyncio
import aiohttp
import concurrent.futures

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils


# Setup logger
logger = logging_utils.setup_logger(prefix="download_media.py")

# Load environment variables
dotenv.load_dotenv()
GOFILE_API_KEY = os.getenv("GOFILE_API_KEY")

# Initialize Apify clients
apify_client_1 = apify_client.ApifyClientAsync(os.getenv("APIFY_API_KEY1"))
apify_client_2 = apify_client.ApifyClientAsync(os.getenv("APIFY_API_KEY2"))

# Rate limiting configuration by API endpoint
ALL_MEDIA_DOWNLOADER_DELAY = 0.1
ALL_VIDEO_DOWNLOADER_DELAY = 0.1
INSTAGRAM_DOWNLOADER_DELAY = 0.3
AUTO_DOWNLOAD_DELAY = 0.4
TELEGRAM_CHANNEL_DELAY = 1.1

# Global semaphores for rate limiting (binary semaphores) by API endpoint
ALL_MEDIA_DOWNLOADER_SEMAPHORE = asyncio.Semaphore(1)
ALL_VIDEO_DOWNLOADER_SEMAPHORE = asyncio.Semaphore(1)
INSTAGRAM_DOWNLOADER_SEMAPHORE = asyncio.Semaphore(1)
AUTO_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(1)
TELEGRAM_CHANNEL_SEMAPHORE = asyncio.Semaphore(1)


async def upload_to_gofile(file_bytes, file_name):
    """
    Upload a file to GoFile and get a direct download link
    
    Args:
        file_bytes: The content of the file as bytes
        file_name: The name to give the file
        
    Returns:
        dict: Information about the uploaded file, including a direct download URL
    """
    max_retries = 5
    for attempt in range(max_retries + 1):  # +1 to allow 5 retries after initial attempt
        try:
            # Upload the file to the server
            upload_url = f'https://upload.gofile.io/uploadfile'
            data = {
                'token': GOFILE_API_KEY,
                'folderId': 'c6e35d76-38ac-4e01-8074-09b2fd299adb'
            }
            
            async with aiohttp.ClientSession() as session:
                form_data = aiohttp.FormData()
                form_data.add_field('file', file_bytes, filename=file_name)
                for key, value in data.items():
                    form_data.add_field(key, value)
                    
                async with session.post(upload_url, data=form_data) as upload_response:
                    upload_response.raise_for_status()
                    upload_data = await upload_response.json()
            
            # Check for bad status in upload response
            if upload_data['status'] != 'ok':
                raise Exception(f"Bad status from GoFile upload. Status: {upload_data['status']}, response: {upload_data}")

            await asyncio.sleep(5)

            # Get direct download link for the uploaded file
            direct_link_url = f"https://api.gofile.io/contents/{upload_data['data']['id']}/directlinks"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {GOFILE_API_KEY}'
            }

            # Get direct download link for the uploaded file
            async with aiohttp.ClientSession() as session:
                async with session.post(direct_link_url, headers=headers) as direct_link_response:
                    direct_link_response.raise_for_status()
                    direct_link_data = await direct_link_response.json()
            
            # Check for bad status in direct link response
            if direct_link_data['status'] != 'ok':
                raise Exception(f"Bad status from GoFile direct link. Status: {direct_link_data['status']}, response: {direct_link_data}")
                
            logger.debug(f"Successfully uploaded file to GoFile. File name: {file_name}")
            return {
                'directLink': direct_link_data['data']['directLink']
            }
            
        except Exception as e:
            if attempt < max_retries:
                logger.error(f"GoFile upload attempt {attempt + 1} failed, retrying in 2 seconds. File name: {file_name}, error: {e}")
                await asyncio.sleep(2)
            else:
                logger.error(f"All {max_retries + 1} GoFile upload attempts failed. File name: {file_name}, error: {e}")
                raise

async def download_media(result, task={}):
    # Extract upload_media parameter from task
    add_subtitles_parameters = task.get("add_subtitles_parameters", {})
    upload_media = add_subtitles_parameters.get("upload_media", True)
    max_duration = add_subtitles_parameters.get("max_duration", float('inf'))
    
    # Handle Dzen short videos using custom scraper
    if "https://dzen.ru/shorts/" in result['url'] or "https://www.dzen.ru/shorts/" in result['url']:
        logger.info(f"Identified as Dzen short video. Result url: {result['url']}")
        
        # Complex page function to extract audio from Dzen shorts
        # This navigates the DOM to find video stream data and downloads audio
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
            "pageFunction": """async function pageFunction(context) {
                function arrayBufferToBase64(buffer) {
                    let binary = '';
                    const bytes = new Uint8Array(buffer);
                    for (let i = 0; i < bytes.byteLength; i++) {
                        binary += String.fromCharCode(bytes[i]);
                    }
                    return btoa(binary);
                }
                
                for (const script of document.querySelectorAll('script')) {
                    const scriptText = script.textContent || script.innerText || '';
                    if (!scriptText.includes('"ssrData":')) continue;
                    
                    const ssrDataKeyIndex = scriptText.indexOf('"ssrData":');
                    const jsonStartIndex = scriptText.lastIndexOf('{', ssrDataKeyIndex);
                    
                    let braceLevel = 0;
                    let jsonEndIndex = -1;
                    for (let j = jsonStartIndex; j < scriptText.length; j++) {
                        if (scriptText[j] === '{') braceLevel++;
                        else if (scriptText[j] === '}') {
                            braceLevel--;
                            if (braceLevel === 0) {
                                jsonEndIndex = j;
                                break;
                            }
                        }
                    }
                    
                    const ssr_data = JSON.parse(scriptText.substring(jsonStartIndex, jsonEndIndex + 1));
                    const videoStreams = ssr_data.ssrData.videoMetaResponse.video.oneVideoStreams;
                    
                    let dashUrl;
                    for (const stream of videoStreams) {
                        if (stream.type === 'dash') {
                            dashUrl = stream.url;
                            break;
                        }
                    }
                    
                    const dashXml = await (await fetch(dashUrl)).text();
                    const xmlDoc = new DOMParser().parseFromString(dashXml, "text/xml");
                    
                    const period = xmlDoc.getElementsByTagName('Period')[0];
                    const audioAdaptationSet = period.getElementsByTagName('AdaptationSet')[1];
                    const baseUrl = audioAdaptationSet.getElementsByTagName('Representation')[2]
                                    .getElementsByTagName('BaseURL')[0].textContent;
                    
                    const urlObj = new URL(dashUrl);
                    const domain = `${urlObj.protocol}//${urlObj.hostname}`;
                    const audioUrl = domain + baseUrl;
                    
                    const audioArrayBuffer = await (await fetch(audioUrl)).arrayBuffer();
                    
                    return {
                        duration: parseInt(ssr_data.ssrData.videoMetaResponse.video.duration),
                        audio_bytes: arrayBufferToBase64(audioArrayBuffer)
                    };
                }
                
                return { duration: null, audio_bytes: null };
            }""",
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
                "apifyProxyCountry": "RU"
            },
            "proxyRotation": "PER_REQUEST",
            "respectRobotsTxtFile": False,
            "runMode": "PRODUCTION",
            "startUrls": [{"url": result['url'], "method": "GET"}],
            "useChrome": False,
            "waitUntil": ["networkidle2"]
        }
        
        logger.info(f"Starting Apify actor call for Dzen short video. Result url: {result['url']}")
        actor_client = apify_client_1.actor("moJRLRc85AitArpNN")
        
        # Retry logic for Apify request
        max_retries = 3
        items_result = None
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Apify actor call attempt {attempt + 1}/{max_retries}. Result url: {result['url']}")
                run = await actor_client.call(run_input=run_input)
                logger.info(f"Apify actor call completed. Dataset ID: {run['defaultDatasetId']}")
                
                dataset_client = apify_client_1.dataset(run["defaultDatasetId"])
                items_result = await dataset_client.list_items()
                
                # Check if response contains audio_bytes
                has_audio_bytes = False
                for item in items_result.items:
                    if item.get('audio_bytes'):
                        has_audio_bytes = True
                        break
                
                if has_audio_bytes:
                    logger.info(f"Successfully received response with audio_bytes on attempt {attempt + 1}")
                    break
                else:
                    logger.warning(f"Response does not contain audio_bytes field on attempt {attempt + 1}/{max_retries}. Result url: {result['url']}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying Apify request in 2 seconds...")
                        await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"Apify actor call failed on attempt {attempt + 1}/{max_retries}. Error: {e}, Result url: {result['url']}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying Apify request in 2 seconds...")
                    await asyncio.sleep(2)
                else:
                    raise
        
        if not items_result or not any(item.get('audio_bytes') for item in items_result.items):
            logging_utils.log_error(logger, f"Failed to get valid response with audio_bytes after {max_retries} attempts. Result url: {result['url']}")
            return None
        
        # Process scraped data and upload to GoFile
        for item in items_result.items:
            duration = item['duration']
            
            # Check if duration exceeds maximum allowed
            if duration >= max_duration:
                result = {
                    "media": [],
                    "duration": duration
                }
                logger.info(f"Duration exceeds maximum allowed, skipping media download. Duration: {duration}, max duration: {max_duration}")
                return result
            
            if not upload_media:
                result = {
                    "media": [],
                    "duration": duration
                }
                logger.info(f"Returning result for Dzen short video without media. Duration: {duration}")
                return result
            
            audio_bytes = base64.b64decode(item['audio_bytes'])
            file_name = f"dzen_short_video_{result['url'].split('/')[-1]}.mp3"
            
            logger.info(f"Uploading audio to GoFile. File name: {file_name}")
            upload_data = await upload_to_gofile(audio_bytes, file_name)
            
            result = {
                "media": [upload_data["directLink"]],
                "duration": duration
            }
            logger.info(f"Returning result for Dzen short video. Media count: {len(result['media'])}, duration: {duration}")
            return result
        
        logging_utils.log_warning(logger, f"No items found in dataset for Dzen short video. Result url: {result['url']}")
        return None
    
    # Handle Dzen long videos using different scraper
    elif "https://dzen.ru/video/" in result['url'] or "https://www.dzen.ru/video/" in result['url']:
        logger.info(f"Identified as Dzen long video. Result url: {result['url']}")
        
        run_input = {
            "mergeAV": False,
            "proxySettings": {
                "useApifyProxy": True,
                "apifyProxyGroups": []
            },
            "url": result['url']
        }
        
        logger.info(f"Starting Apify actor call for Dzen long video. Result url: {result['url']}")
        actor_client = apify_client_2.actor("hVlkT1FrZB15YsUDo")
        run = await actor_client.call(run_input=run_input)
        logger.info(f"Apify actor call completed. Dataset ID: {run['defaultDatasetId']}")

        dataset_client = apify_client_2.dataset(run["defaultDatasetId"])
        items_result = await dataset_client.list_items()
        
        # Process video formats and select best audio quality
        for item in items_result.items:
            duration = item.get('duration', 0)
            logger.info(f"Media duration: {duration} seconds")
            
            # Check if duration exceeds maximum allowed
            if duration >= max_duration:
                result = {
                    "media": [],
                    "duration": duration
                }
                logger.info(f"Duration exceeds maximum allowed, skipping media download. Duration: {duration}, max duration: {max_duration}")
                return result
            
            if not upload_media:
                result = {
                    "media": [],
                    "duration": duration
                }
                logger.info(f"Returning result for Dzen long video without media. Duration: {duration}")
                return result
            
            audio_formats = [f for f in item['formats'] if f.get('resolution') == 'audio only']
            logger.info(f"Found audio formats. Format count: {len(audio_formats)}")
            logger.debug(f"Audio formats details: {json.dumps(audio_formats, indent=4, ensure_ascii=False)}")
            
            if len(audio_formats) == 0:
                logging_utils.log_error(logger, "No audio formats found in scraped data")
                continue
            
            # Select audio format (prefer higher quality but cap at index 4)
            audio_format_index = min(4, len(audio_formats) - 1)
            audio_url = audio_formats[audio_format_index]['url']
            logger.info(f"Selected audio format. Index: {audio_format_index}, audio url: {audio_url}")

            # Headers to mimic browser request
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
                'Cache-Control': 'max-age=0',
                'Connection': 'keep-alive',
                'If-Modified-Since': 'Wed, 1 Jan 2014 00:00:00 GMT',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
                'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }
            
            cookies = {'tstc': 'p'}

            logger.info(f"Downloading media content. Audio url: {audio_url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(audio_url, headers=headers, cookies=cookies) as audio_response:
                    audio_response.raise_for_status()
                    content = await audio_response.read()
                    logger.info(f"Download completed. Status code: {audio_response.status}")
            
            file_name = f"dzen_long_video_{result['url'].split('/')[-1]}.mp3"
            logger.info(f"Uploading audio to GoFile. File name: {file_name}")
            
            upload_data = await upload_to_gofile(content, file_name)
            
            result = {
                "media": [upload_data["directLink"]],
                "duration": duration
            }
            logger.info(f"Returning result for Dzen long video. Media count: {len(result['media'])}, duration: {duration}")
            return result

    # Handle VK videos using RapidAPI
    elif "https://vk.com/" in result['url'] or "https://www.vk.com/" in result['url']:
        logger.info(f"Identified as VK video. Result url: {result['url']}")
        
        api_url = "https://all-media-downloader1.p.rapidapi.com/all"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-rapidapi-host": "all-media-downloader1.p.rapidapi.com",
            "x-rapidapi-key": "ebfc131555msh1b99dcb2063f177p1350d6jsnc0cc0c9bcbcc"
        }
        payload = {"url": result['url']}
        
        logger.info(f"Calling RapidAPI for VK video. Result url: {result['url']}")
        
        async with ALL_MEDIA_DOWNLOADER_SEMAPHORE:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_url, headers=headers, data=payload) as response:
                        response.raise_for_status()
                        response_data = await response.json()
            finally:
                await asyncio.sleep(ALL_MEDIA_DOWNLOADER_DELAY)
        
        # Select best audio format or fallback to video
        audio_url = None
        formats = response_data.get("formats", [])
        logger.info(f"Found formats from API. Format count: {len(formats)}")
        
        audio_formats = [f for f in formats if "audio only" in f.get("format", "") and f.get("ext") == "m4a"]
        logger.info(f"Found audio-only formats. Audio format count: {len(audio_formats)}")
        
        if audio_formats:
            audio_format = audio_formats[-1]
            audio_url = audio_format["url"]
            logger.info(f"Selected best audio format. ABR: {audio_format.get('abr')}, audio url: {audio_url}")
        else:
            video_formats = [f for f in formats if f.get("vcodec") != "none"]
            if video_formats:
                video_format = video_formats[0]
                audio_url = video_format["url"]
                logger.info(f"Using video format as fallback. Audio url: {audio_url}")
        
        duration = response_data.get("duration", 0)
        logger.info(f"Media duration: {duration} seconds")
        
        # Check if duration exceeds maximum allowed
        if duration >= max_duration:
            result = {
                "media": [],
                "duration": duration
            }
            logger.info(f"Duration exceeds maximum allowed, skipping media download. Duration: {duration}, max duration: {max_duration}")
            return result
        
        if not upload_media:
            result = {
                "media": [],
                "duration": duration
            }
            logger.info(f"Returning result for VK video without media. Duration: {duration}")
            return result

        # Headers for media download
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'If-Modified-Since': 'Wed, 1 Jan 2014 00:00:00 GMT',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
        
        cookies = {'tstc': 'p'}

        logger.info(f"Downloading media content. Audio url: {audio_url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(audio_url, headers=headers, cookies=cookies) as audio_response:
                audio_response.raise_for_status()
                content = await audio_response.read()
                logger.info(f"Download completed. Status code: {audio_response.status}")
        
        file_name = f"audio_{result['url'].split('/')[-1]}.mp4"
        logger.info(f"Uploading audio to GoFile. File name: {file_name}")
        upload_data = await upload_to_gofile(content, file_name)
            
        result = {
            "media": [upload_data["directLink"]],
            "duration": duration
        }
        logger.info(f"Returning result for VK video. Media count: {len(result['media'])}, duration: {duration}")
        return result

    # Handle Twitch videos and clips
    elif "twitch.tv" in result['url']:
        logger.info(f"Identified as Twitch video. Result url: {result['url']}")
        
        api_url = "https://all-video-downloader1.p.rapidapi.com/all"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-rapidapi-host": "all-video-downloader1.p.rapidapi.com",
            "x-rapidapi-key": "ebfc131555msh1b99dcb2063f177p1350d6jsnc0cc0c9bcbcc"
        }
        payload = {"url": result['url']}
        
        logger.info(f"Calling RapidAPI for Twitch video. Result url: {result['url']}")
        
        async with ALL_VIDEO_DOWNLOADER_SEMAPHORE:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_url, headers=headers, data=payload) as response:
                        response.raise_for_status()
                        response_data = await response.json()
            finally:
                await asyncio.sleep(ALL_VIDEO_DOWNLOADER_DELAY)
        
        # Select best available format (prefer audio-only)
        media_url = None
        formats = response_data["formats"]
        logger.info(f"Found formats from API. Format count: {len(formats)}")
        
        # Look for audio-only format first
        for format_obj in formats:
            if format_obj["format_id"] == "Audio_Only":
                media_url = format_obj["url"]
                logger.info(f"Found Audio_Only format. Media url: {media_url}")
                break
        
        # Fallback to mp4 format
        if not media_url:
            for format_obj in formats:
                if format_obj["ext"] == "mp4":
                    media_url = format_obj["url"]
                    logger.info(f"Using mp4 format as fallback. Media url: {media_url}")
                    break
        
        # Final fallback to first available format
        if not media_url and formats:
            media_url = formats[0]["url"]
            logger.info(f"Using first available format. Media url: {media_url}")
        
        duration = response_data["duration"]
        logger.info(f"Media duration: {duration} seconds")
        
        # Check if duration exceeds maximum allowed
        if duration >= max_duration:
            result = {
                "media": [],
                "duration": duration
            }
            logger.info(f"Duration exceeds maximum allowed, skipping media download. Duration: {duration}, max duration: {max_duration}")
            return result
        
        if not upload_media:
            result = {
                "media": [],
                "duration": duration
            }
            logger.info(f"Returning result for Twitch video without media. Duration: {duration}")
            return result
        
        # Handle m3u8 streams with FFmpeg processing
        if ".m3u8" in media_url:
            logger.info(f"Detected m3u8 stream, processing with FFmpeg. Media url: {media_url}")
            clip_id = result['url'].split('/')[-1]
            file_name = f"twitch_clip_{clip_id}.mp4"
            
            # Create temporary file for FFmpeg output
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                logger.info(f"Created temporary file for FFmpeg processing. Temp file: {temp_file.name}")
                ffmpeg_command = (
                    ffmpeg.FFmpeg()
                    .option("y")
                    .input(media_url)
                    .output(
                        temp_file.name,
                        {"c:v": "copy", "c:a": "copy"}
                    )
                )
                
                logger.info("Starting FFmpeg execution for m3u8 processing")
                # Run FFmpeg in executor to avoid blocking the async loop
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(executor, ffmpeg_command.execute)
                logger.info("FFmpeg execution completed")
                
                # Read processed file and upload
                with open(temp_file.name, 'rb') as f:
                    content = f.read()
                    logger.info(f"Uploading FFmpeg output to GoFile. File name: {file_name}")
                    upload_data = await upload_to_gofile(content, file_name)
            
            logger.info(f"Removing temporary file. Temp file: {temp_file.name}")
            os.unlink(temp_file.name)

            result = {
                "media": [upload_data["directLink"]],
                "duration": duration
            }
            logger.info(f"Returning result for Twitch video. Media count: {len(result['media'])}, duration: {duration}")
            return result
        else:
            # Direct URL, no processing needed
            result = {
                "media": [media_url],
                "duration": duration
            }
            logger.info(f"Returning result for Twitch video. Media count: {len(result['media'])}, duration: {duration}")
            return result

    # Handle Instagram posts and reels
    elif "https://instagram.com/" in result['url'] or "https://www.instagram.com/" in result['url']:
        logger.info(f"Identified as Instagram post. Result url: {result['url']}")
        
        api_url = "https://instagram-looter2.p.rapidapi.com/post-dl"
        headers = {
            "x-rapidapi-host": "instagram-looter2.p.rapidapi.com",
            "x-rapidapi-key": "ebfc131555msh1b99dcb2063f177p1350d6jsnc0cc0c9bcbcc"
        }
        
        params = {"url": result['url']}
        logger.info(f"Calling RapidAPI for Instagram content. Result url: {result['url']}")
        
        async with INSTAGRAM_DOWNLOADER_SEMAPHORE:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, headers=headers, params=params) as response:
                        response.raise_for_status()
                        response_data = await response.json()
            finally:
                await asyncio.sleep(INSTAGRAM_DOWNLOADER_DELAY)
        
        # Check if API call was successful
        if not response_data.get("status"):
            logging_utils.log_error(logger, f"Instagram API returned unsuccessful status. Result url: {result['url']}")
            return None
        
        result_data = {"media": []}
        
        # Process media items from data.medias array
        data = response_data.get("data", {})
        media_items = data.get("medias", [])
        logger.info(f"Found media items from Instagram API. Media count: {len(media_items)}")
        
        for media_item in media_items:
            media_type = media_item.get("type", "")
            download_url = media_item.get("link", "")
            
            # Check if this is a video
            if media_type == "video" and download_url:
                logger.info(f"Found video media. Download url: {download_url}, type: {media_type}")
                if upload_media:
                    result_data["media"].append(download_url)
        
        if not upload_media:
            logger.info(f"Returning result for Instagram content without media")
        else:
            logger.info(f"Returning result for Instagram content. Media count: {len(result_data['media'])}")
        return result_data

    # Handle YouTube videos
    elif "youtube.com/" in result['url'] or "https://www.youtube.com/" in result['url']:
        logger.info(f"Identified as YouTube video. Result url: {result['url']}")
        
        api_url = "https://auto-download-all-in-one.p.rapidapi.com/v1/social/autolink"
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-host": "auto-download-all-in-one.p.rapidapi.com",
            "x-rapidapi-key": "ebfc131555msh1b99dcb2063f177p1350d6jsnc0cc0c9bcbcc"
        }
        payload = {"url": result['url']}
        
        logger.info(f"Calling RapidAPI for YouTube video. Result url: {result['url']}")
        
        async with AUTO_DOWNLOAD_SEMAPHORE:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_url, headers=headers, json=payload) as response:
                        response.raise_for_status()
                        response_data = await response.json()
            finally:
                await asyncio.sleep(AUTO_DOWNLOAD_DELAY)
        
        # Select best audio quality available
        audio_url = None
        duration = response_data.get("duration", 0)
        logger.info(f"Video duration: {duration} seconds")
        
        # Check if duration exceeds maximum allowed
        if duration >= max_duration:
            result = {
                "media": [],
                "duration": duration
            }
            logger.info(f"Duration exceeds maximum allowed, skipping media download. Duration: {duration}, max duration: {max_duration}")
            return result
        
        # Prefer medium quality m4a audio with 48kHz sample rate
        for media in response_data["medias"]:
            if media["type"] == "audio" and media["ext"] == "m4a" and media["audioQuality"] == "AUDIO_QUALITY_MEDIUM" and media["audioSampleRate"] == "48000":
                audio_url = media["url"]
                logger.info(f"Found medium quality m4a audio. Audio url: {audio_url}")
                break
        
        # Fallback to any available audio format
        if not audio_url:
            for media in response_data["medias"]:
                if media["type"] == "audio":
                    audio_url = media["url"]
                    logger.info(f"Using first available audio as fallback. Audio url: {audio_url}")
                    break

        if upload_media:
            result = {
                "media": [audio_url],
                "duration": duration
            }
            logger.info(f"Returning result for YouTube video. Media count: {len(result['media'])}, duration: {duration}")
        else:
            result = {
                "media": [],
                "duration": duration
            }
            logger.info(f"Returning result for YouTube video without media. Duration: {duration}")
        return result

    # Handle Telegram posts and channels
    elif "https://t.me/" in result['url'] or "https://www.t.me/" in result['url']:
        logger.info(f"Identified as Telegram post. Result url: {result['url']}")
            
        # Parse Telegram URL to extract channel and message ID
        channel_parts = result['url'].split('t.me/')
        if len(channel_parts) > 1 and channel_parts[1].strip():
            channel_path = channel_parts[1].split('/')
            
            # Check if we have at least one part (the channel name)
            if len(channel_path) == 0 or not channel_path[0].strip():
                logging_utils.log_error(logger, f"Invalid Telegram URL format - no channel found. Result url: {result['url']}")
            
            channel = channel_path[0]
            logger.info(f"Extracted Telegram channel. Channel: {channel}")
            
            max_id = 10
            limit = 1
            
            # Check if we have a message ID (second part)
            if len(channel_path) > 1 and channel_path[-1].isdigit():
                max_id = channel_path[-1]
                logger.info(f"Extracted message ID. Message ID: {max_id}")
            
            api_url = f"https://telegram-channel.p.rapidapi.com/channel/message"
            headers = {
                "x-rapidapi-host": "telegram-channel.p.rapidapi.com",
                "x-rapidapi-key": "ebfc131555msh1b99dcb2063f177p1350d6jsnc0cc0c9bcbcc"
            }
            params = {
                "channel": channel,
                "limit": limit,
                "max_id": max_id
            }
            
            logger.info(f"Calling RapidAPI for Telegram channel. Channel: {channel}, message ID: {max_id}")
            
            async with TELEGRAM_CHANNEL_SEMAPHORE:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(api_url, headers=headers, params=params) as response:
                            response.raise_for_status()
                            response_data = await response.json()
                finally:
                    await asyncio.sleep(TELEGRAM_CHANNEL_DELAY)
            
            result = {"media": []}
            
            # Validate API response format
            if not isinstance(response_data, list):
                logging_utils.log_warning(logger, f"Unexpected response format from Telegram API. Response type: {type(response_data)}")
            
            # Process messages for audio and video content
            for message in response_data:
                # Handle audio content
                if message.get("audio") and message["audio"].get("url"):
                    duration_str = message["audio"].get("duration", "0:00")
                    logger.info(f"Found audio content. Duration: {duration_str}")
                    
                    # Parse duration string to seconds
                    duration_parts = duration_str.split(":")
                    duration_seconds = 0
                    try:
                        if len(duration_parts) == 2:
                            duration_seconds = int(duration_parts[0]) * 60 + int(duration_parts[1])
                        elif len(duration_parts) == 3:
                            duration_seconds = int(duration_parts[0]) * 3600 + int(duration_parts[1]) * 60 + int(duration_parts[2])
                    except (ValueError, IndexError) as e:
                        logging_utils.log_warning(logger, f"Failed to parse audio duration. Duration string: {duration_str}, error: {e}")
                        duration_seconds = 0
                    
                    logger.info(f"Adding audio content. Audio url: {message['audio']['url']}, duration: {duration_seconds}s")
                    
                    # Check if duration exceeds maximum allowed
                    if duration_seconds >= max_duration:
                        result = {
                            "media": [],
                            "duration": duration_seconds
                        }
                        logger.info(f"Duration exceeds maximum allowed, skipping media download. Duration: {duration_seconds}, max duration: {max_duration}")
                        return result
                    
                    if upload_media:
                        result["media"].append(message["audio"]["url"])
                    if "duration" not in result:
                        result["duration"] = duration_seconds
                
                # Handle video content
                if message.get("video") and message["video"].get("url"):
                    duration_str = message["video"].get("duration", "0:00")
                    logger.info(f"Found video content. Duration: {duration_str}")
                    
                    # Parse duration string to seconds
                    duration_parts = duration_str.split(":")
                    duration_seconds = 0
                    try:
                        if len(duration_parts) == 2:
                            duration_seconds = int(duration_parts[0]) * 60 + int(duration_parts[1])
                        elif len(duration_parts) == 3:
                            duration_seconds = int(duration_parts[0]) * 3600 + int(duration_parts[1]) * 60 + int(duration_parts[2])
                    except (ValueError, IndexError) as e:
                        logging_utils.log_warning(logger, f"Failed to parse video duration. Duration string: {duration_str}, error: {e}")
                        duration_seconds = 0
                    
                    logger.info(f"Adding video content. Video url: {message['video']['url']}, duration: {duration_seconds}s")
                    
                    # Check if duration exceeds maximum allowed
                    if duration_seconds >= max_duration:
                        result = {
                            "media": [],
                            "duration": duration_seconds
                        }
                        logger.info(f"Duration exceeds maximum allowed, skipping media download. Duration: {duration_seconds}, max duration: {max_duration}")
                        return result
                    
                    if upload_media:
                        result["media"].append(message["video"]["url"])
                    if "duration" not in result:
                        result["duration"] = duration_seconds
            
            if upload_media:
                logger.info(f"Returning result for Telegram post. Media count: {len(result['media'])}")
            else:
                logger.info(f"Returning result for Telegram post without media. Duration: {result.get('duration', 0)}")
            return result
        else:
            logging_utils.log_error(logger, f"Invalid Telegram URL format. Result url: {result['url']}")

    return {}
