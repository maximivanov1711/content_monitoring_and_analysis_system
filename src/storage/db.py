import os
import asyncpg
import asyncio
import json
import sys
from typing import Optional, Dict, Any, List
from functools import wraps
from datetime import datetime, timedelta

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils


# Setup logger
logger = logging_utils.setup_logger('db.py')

def make_json_safe(obj, visited=None):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, bytes):
        try:
            return obj.decode('utf-8', 'replace')
        except Exception:
            return str(obj)
    if isinstance(obj, (list, tuple, set, frozenset)):
        if visited is None:
            visited = set()
        obj_id = id(obj)
        if obj_id in visited:
            return None
        visited.add(obj_id)
        return [make_json_safe(item, visited) for item in obj]
    if isinstance(obj, dict):
        if visited is None:
            visited = set()
        obj_id = id(obj)
        if obj_id in visited:
            return None
        visited.add(obj_id)
        result = {}
        for k, v in obj.items():
            try:
                key_str = str(k)
            except Exception:
                key_str = repr(k)
            result[key_str] = make_json_safe(v, visited)
        return result
    try:
        return str(obj)
    except Exception:
        return None

# Singleton class to ensure only one pool instance across all imports
class DatabasePool:
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabasePool, cls).__new__(cls)
            cls._instance._pool = None
            cls._instance._initialized = False
        return cls._instance
    
    async def get_pool(self):
        """Get or create the database connection pool."""
        # First check if already initialized (quick check with lock)
        async with self._lock:
            if self._initialized and self._pool:
                return self._pool
        
        # Do the expensive I/O operation outside the lock
        logger.info("Starting database pool initialization")
        try:
            # Get connection string from environment variable
            DATABASE_URL = os.environ.get("DATABASE_URL")
            
            logger.info("Initializing database connection pool")
        
            # Create a connection pool (outside the lock to prevent deadlock)
            pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=4,
                max_inactive_connection_lifetime=30,
                command_timeout=300,
                timeout=10
            )
            
            # Now acquire lock to set the result (with double-check for race conditions)
            async with self._lock:
                # Double-check in case another coroutine initialized while we were creating the pool
                if self._initialized and self._pool:
                    # Another coroutine beat us to it, close our pool and return the existing one
                    await pool.close()
                    return self._pool
                
                # Set both values after everything succeeds
                self._pool = pool
                self._initialized = True
                
                logger.info("Database connection pool initialized successfully")
                return self._pool
                
        except Exception as e:
            logging_utils.log_error(logger, "Failed to initialize database connection pool", e)
            raise
    
    async def _initialize(self):
        """Initialize the database connection pool."""
        return await self.get_pool()

# Global singleton instance
_db_pool = DatabasePool()


def retry_db_operation(max_retries: int = 5, delay: float = 1.0):
    """Decorator to retry database operations with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)
                        logging_utils.log_warning(logger, f"Database operation {func.__name__} failed: {str(e)}. Retrying in {wait_time}s, (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        logging_utils.log_error(logger, f"Database operation {func.__name__} failed after {max_retries} attempts: {str(e)}")
            
            if last_exception:
                raise last_exception
            else:
                raise RuntimeError(f"Database operation {func.__name__} failed after {max_retries} attempts with no exception captured")
        
        return wrapper
    return decorator


async def initialize_db_pool():
    """Initialize the database connection pool."""
    return await _db_pool._initialize()


async def get_pool():
    """Get or create the database connection pool."""
    pool = await _db_pool.get_pool()
    if not pool:
        raise RuntimeError("Database pool is not available")
    return pool


@retry_db_operation(max_retries=3)
async def save_post(url: str, data: Dict[str, Any], fields_to_update: Optional[List[str]] = None) -> bool:
    """Store post data in the database."""
    logger.debug(f"Storing post data. Result url: {url}")
    
    pool = await get_pool()
        
    async with pool.acquire() as conn:
        if fields_to_update:
            # Update only specific fields
            for field_path in fields_to_update:
                field_value = data
                try:
                    for key in field_path.split('.'):
                        field_value = field_value[key]
                except KeyError:
                    logger.debug(f"Field path '{field_path}' not found in data, skipping update")
                    continue
                
                path_components = field_path.split('.')
                await conn.execute(
                    '''
                    INSERT INTO post_cache (url, data, creation_time)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (url) 
                    DO UPDATE SET data = jsonb_set(post_cache.data, $3, $4), creation_time = NOW()
                    ''',
                    url, json.dumps(data, ensure_ascii=False), 
                    path_components,
                    json.dumps(field_value, ensure_ascii=False), 
                    timeout=100000
                )
        else:
            # Update entire data (current behavior)
            await conn.execute(
                '''
                INSERT INTO post_cache (url, data, creation_time)
                VALUES ($1, $2, NOW())
                ON CONFLICT (url) 
                DO UPDATE SET data = $2, creation_time = NOW()
                ''',
                url, json.dumps(data, ensure_ascii=False), timeout=100000
            )
        
        logger.debug(f"Successfully stored post data Result url: {url}")
        return True


@retry_db_operation(max_retries=3)
async def get_post(url: str) -> Optional[Dict[str, Any]]:
    """Retrieve post data from the database."""
    logger.debug(f"Getting post data. Result url: {url}")
    
    pool = await get_pool()
        
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            'SELECT data FROM post_cache WHERE url = $1',
            url,
            timeout=100000
        )
        
        if result:
            logger.debug(f"Found post data. Result url: {url}")
            return json.loads(result)
        
        logger.debug(f"No post data found. Result url: {url}")
        return None


@retry_db_operation(max_retries=3)
async def save_profile(url: str, data: Dict[str, Any], fields_to_update: Optional[List[str]] = None) -> bool:
    """Store profile data in the database."""
    logger.debug(f"Storing profile data. Profile url: {url}")
    
    # Add updated_date to the data object
    data['updated_date'] = datetime.now().isoformat()
    
    pool = await get_pool()
        
    async with pool.acquire() as conn:
        if fields_to_update:
            # Update only specific fields
            for field_path in fields_to_update:
                field_value = data
                try:
                    for key in field_path.split('.'):
                        field_value = field_value[key]
                except KeyError:
                    logger.debug(f"Field path '{field_path}' not found in data, skipping update")
                    continue
                
                path_components = field_path.split('.')
                await conn.execute(
                    '''
                    INSERT INTO profile_cache (url, data, creation_time)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (url) 
                    DO UPDATE SET data = jsonb_set(profile_cache.data, $3, $4), creation_time = NOW()
                    ''',
                    url, json.dumps(data, ensure_ascii=False), 
                    path_components,
                    json.dumps(field_value, ensure_ascii=False), 
                    timeout=100000
                )
        else:
            # Update entire data (current behavior)
            await conn.execute(
                '''
                INSERT INTO profile_cache (url, data, creation_time)
                VALUES ($1, $2, NOW())
                ON CONFLICT (url) 
                DO UPDATE SET data = $2, creation_time = NOW()
                ''',
                url, json.dumps(data, ensure_ascii=False), timeout=100000
            )
        
        logger.debug(f"Successfully stored profile data. Profile url: {url}")
        return True


@retry_db_operation(max_retries=3)
async def get_profile(url: str, refresh_profile_data: bool = False) -> Optional[Dict[str, Any]]:
    """Retrieve profile data from the database."""
    logger.debug(f"Getting profile data. Profile url: {url}")
    
    pool = await get_pool()
        
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            'SELECT data FROM profile_cache WHERE url = $1',
            url,
            timeout=100000
        )
        
        if result:
            profile_data = json.loads(result)
            
            # Check if refresh_profile_data is True and updated_date is older than one day
            if refresh_profile_data and 'updated_date' in profile_data:
                try:
                    updated_date = datetime.fromisoformat(profile_data['updated_date'])
                    one_day_ago = datetime.now() - timedelta(hours=12)
                    
                    if updated_date < one_day_ago:
                        logger.debug(f"Profile data is older than one day and refresh requested. Profile url: {url}")
                        return None
                except (ValueError, TypeError) as e:
                    logger.debug(f"Could not parse updated_date, returning None. Profile url: {url}, error: {e}")
                    return None
            
            logger.debug(f"Found profile data. Profile url: {url}")
            return profile_data
        
        logger.debug(f"No profile data found. Profile url: {url}")
        return None


@retry_db_operation(max_retries=3)
async def check_posts_exist(urls: list) -> set:
    """Check which URLs already exist in the post_cache table.
    
    Args:
        urls (list): List of URLs to check
        
    Returns:
        set: Set of URLs that exist in the database
    """
    logger.debug(f"Checking existence of {len(urls)} posts in post_cache")
    
    pool = await get_pool()
        
    async with pool.acquire() as conn:
        result = await conn.fetch(
            'SELECT url FROM post_cache WHERE url = ANY($1)',
            urls,
            timeout=100000
        )
        
        existing_urls = {row['url'] for row in result}
        logger.debug(f"Found {len(existing_urls)} existing posts out of {len(urls)} checked")
        return existing_urls


@retry_db_operation(max_retries=3)
async def get_posts_by_sql(sql_query: str, *params) -> Optional[List[Dict[str, Any]]]:
    """Execute a direct SQL query and return results if any.
    
    Args:
        sql_query (str): The SQL query to execute
        *params: Parameters for the SQL query
        
    Returns:
        Optional[List[Dict[str, Any]]]: Query results for SELECT queries, None for other queries
    """
    logger.debug(f"Executing SQL query: {sql_query}")
    
    pool = await get_pool()
        
    async with pool.acquire() as conn:
        result = await conn.fetch(sql_query, *params, timeout=100000)
        results = [json.loads(row['data']) for row in result]
        return results