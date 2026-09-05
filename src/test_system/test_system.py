
import sys
import asyncio
import json5

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils
if __name__ == "__main__":
    logging_utils.initialize_logging()
from src import main
from src.notify import notify

# Setup logger
logger = logging_utils.setup_logger(prefix='test_system.py', write_to_file=False)


async def test_system():
    logger.info('Starting system test')
    
    task = json5.load(open("tasks/task_test.json5", "r"))
    
    await main.start(task=task)

    if len(logging_utils.errors) > 0:
        notification_message = f'System test failed. Number of errors: {len(logging_utils.errors)}\nErrors:'

        for error in logging_utils.errors:
            notification_message += f'\nError ID: {error["error_id"]}\nError message: {error["error_message"]}\nError traceback: {error["error_traceback"]}'

        notify.notify(notification_message, notification_type='private')
        
        return False
    
    logger.info('System test passed')
    return True


if __name__ == "__main__":
    # Manual test
    logger.info(asyncio.run(test_system()))