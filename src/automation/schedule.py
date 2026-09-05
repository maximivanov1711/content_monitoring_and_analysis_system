from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import sys

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils
from src.automation import execute


# Setup logger
logger = logging_utils.setup_logger('scheduler.py')

# Global scheduler instance
scheduler = AsyncIOScheduler()

# Store job ID for unscheduling
current_job_id = None


def schedule(task={}):
    """
    Schedule a task to run according to a cron expression.
    
    Args:
        task (dict): Task configuration
        cron_expression (str): Cron expression defining the schedule
    """
    global current_job_id

    logger.info(f"Starting schedule.py")
    
    # Start scheduler if not already started
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
    
    # Unschedule any existing job
    if current_job_id:
        logger.info(f"Unscheduling existing task")
        unschedule()
        
    # Parse the cron expression
    trigger = CronTrigger.from_crontab(task["cron_expression"])
    
    # Add the job to the scheduler with the execute function
    job = scheduler.add_job(
        execute.execute,
        trigger=trigger,
        args=[task],
        id='task_execution_job',
        replace_existing=True
    )
    current_job_id = job.id

    logger.info(f"Finished schedule.py")


def unschedule():
    """
    Unschedule the current task.
    """
    global current_job_id
    
    if current_job_id:
        scheduler.remove_job(current_job_id)
        current_job_id = None

        logger.info(f"Task unscheduled successfully")
