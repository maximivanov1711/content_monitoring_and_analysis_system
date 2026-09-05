import sys
from pathlib import Path
import shutil

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils
import json
from datetime import datetime

# Setup logger
logger = logging_utils.setup_logger('local_storage.py')


def save_results_locally(data, prefix):
    """
    Save results to local file before exporting.
    
    Args:
        data: Data to save
        filename_prefix (str): Prefix for the filename
        
    Returns:
        str: Path to saved file
    """
    try:
        target_dir = Path(f"data/{prefix}")
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Move existing files to previous folder
        existing_files = [f for f in target_dir.iterdir() if f.is_file()]
        if existing_files:
            previous_dir = target_dir / "previous"
            previous_dir.mkdir(exist_ok=True)
            
            for file in existing_files:
                destination = previous_dir / file.name
                shutil.move(str(file), str(destination))
                logger.info(f"Moved existing file to previous folder. File: {file.name}")
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{prefix}_{timestamp}.json"
        filepath = target_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        logger.info(f"Results saved locally to: {filepath}")

        return str(filepath)
        
    except Exception as e:
        logging_utils.log_error(logger, f"Error saving results locally", e)
        return None