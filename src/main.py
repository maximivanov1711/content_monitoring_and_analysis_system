import json5
import signal
import sys
import asyncio

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils
if __name__ == "__main__":
    logging_utils.initialize_logging()

from src.storage import db
from src.notify import notify
from src.automation import execute
from src.automation import schedule
from src.test_system import test_system

# Setup logger
logger = logging_utils.setup_logger('main.py')


def terminate(sig, frame):
    """
    Handle termination signals to ensure clean shutdown.
    """
    logger.info("Termination signal received, shutting down")
    schedule.unschedule()
    sys.exit(0)


async def start(task={}):
    try:
        # Initialize the database
        await db.initialize_db_pool()

        # Set up signal handling for graceful termination
        signal.signal(signal.SIGINT, terminate)
        signal.signal(signal.SIGTERM, terminate)

        # Enable notifications if specified in the task
        notify.NOTIFICATIONS_ENABLED = task.get('notify_parameters',
                                                {}).get('enabled', False)

        # Test all modules before starting the system
        if task.get('test_parameters', {}).get('enabled', False):
            test_passed = await test_system.test_system()
            if not test_passed:
                logging_utils.log_error(logger,
                                        "System test failed, shutting down")
                sys.exit(1)

        # Execute the task immediately or schedule its reccurring execution
        if task.get('start_immediately', False):
            logger.info("task.start_immediately is True, executing now")
            await execute.execute(task)
            logger.info("Immediate execution completed successfully")
            sys.exit(0)
        else:
            logger.info("task.start_immediately is False, scheduling task")
            schedule.schedule(task)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
        schedule.unschedule()
        sys.exit(0)
    except Exception as e:
        logging_utils.log_error(logger, "Error in main.main()", e)
        schedule.unschedule()
        sys.exit(1)


async def main(task={}):
    """Main function to run the task scheduler and executor."""
    logger.info("========== STARTING THE SYSTEM ==========")
    notify.notify("Starting the system", "private")

    try:
        await start(task)
    except Exception:
        pass
    else:
        logger.info("========== THE SYSTEM IS READY ==========")

        # Keep the main thread alive
        while True:
            signal.pause()


if __name__ == "__main__":
    # Manual run
    task = json5.load(open("tasks/task_daily_standard.json5", "r"))
    # task = json5.load(open("tasks/task_export.json5", "r"))
    asyncio.run(main(task=task))
