"""
Logging utility module for setting up consistent logging across the application.
"""
import os
import sys
import logging
import traceback
import uuid
from datetime import datetime
import glob
import re
import shutil

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.notify import notify


errors = []


# Terminal color codes
COLORS = {
    'RED': '\033[91m',
    'YELLOW': '\033[93m',
    'BLUE': '\033[94m',
    'RESET': '\033[0m'
}

# Global variables to track if logging has been initialized
_logging_initialized = False
_main_log_file_path = None


# Custom formatter that adds colors to log messages based on log level.
class ColoredFormatter(logging.Formatter):
    """
    Custom formatter that adds colors to log messages based on log level.
    """
    def format(self, record):
        # Save original levelname to restore later
        original_levelname = record.levelname
        
        # Add colors based on log level
        if record.levelno >= logging.ERROR:
            record.levelname = f"{COLORS['RED']}{record.levelname}{COLORS['RESET']}"
        elif record.levelno >= logging.WARNING:
            record.levelname = f"{COLORS['YELLOW']}{record.levelname}{COLORS['RESET']}"
        elif record.levelno >= logging.INFO:
            record.levelname = f"{COLORS['BLUE']}{record.levelname}{COLORS['RESET']}"
        
        # Format the message
        result = super().format(record)
        
        # Restore original levelname
        record.levelname = original_levelname
        return result


def move_previous_logs():
    """
    Move all previous log files to a timestamped folder based on the main log file timestamp.
    """
    logs_dir = './logs'
    
    # Find existing main log files with timestamp pattern
    log_pattern = os.path.join(logs_dir, 'log_last_*.log')
    main_log_files = glob.glob(log_pattern)
    
    # Also check for the old format log_last.log
    old_log_file = os.path.join(logs_dir, 'log_last.log')
    if os.path.exists(old_log_file):
        main_log_files.append(old_log_file)
    
    if not main_log_files:
        return
    
    # Get all log files (including error logs)
    all_log_files = glob.glob(os.path.join(logs_dir, '*.log'))
    
    # Check if errors folder exists
    errors_dir = os.path.join(logs_dir, 'errors')
    errors_folder_exists = os.path.exists(errors_dir) and os.path.isdir(errors_dir)
    
    if not all_log_files and not errors_folder_exists:
        return
    
    # Extract timestamp from the newest main log file, or use current time for old format
    newest_main_log = max(main_log_files, key=os.path.getmtime)
    
    if 'log_last_' in os.path.basename(newest_main_log) and newest_main_log != old_log_file:
        # Extract timestamp from filename
        filename = os.path.basename(newest_main_log)
        timestamp_match = re.search(r'log_last_(\d{8}_\d{6})\.log', filename)
        if timestamp_match:
            timestamp_str = timestamp_match.group(1)
        else:
            # Fallback to file modification time
            mod_time = datetime.fromtimestamp(os.path.getmtime(newest_main_log))
            timestamp_str = mod_time.strftime('%Y%m%d_%H%M%S')
    else:
        # For old format or if timestamp extraction fails, use file modification time
        mod_time = datetime.fromtimestamp(os.path.getmtime(newest_main_log))
        timestamp_str = mod_time.strftime('%Y%m%d_%H%M%S')
    
    # Create timestamped folder
    archive_folder = os.path.join(logs_dir, timestamp_str)
    os.makedirs(archive_folder, exist_ok=True)
    
    # Move all log files to the archive folder
    for log_file in all_log_files:
        if os.path.isfile(log_file):
            filename = os.path.basename(log_file)
            dest_path = os.path.join(archive_folder, filename)
            try:
                shutil.move(log_file, dest_path)
            except (OSError, shutil.Error):
                pass
    
    # Move errors folder to the archive folder if it exists
    if errors_folder_exists:
        errors_dest_path = os.path.join(archive_folder, 'errors')
        try:
            shutil.move(errors_dir, errors_dest_path)
        except (OSError, shutil.Error):
            pass


def initialize_logging():
    """
    Initialize the global logging system once. This should be called only once from main.py.
    Handles moving previous logs and creating the main timestamped log file.
    
    Returns:
        str: Path to the main log file created
    """
    global _logging_initialized, _main_log_file_path
    
    if _logging_initialized:
        return _main_log_file_path
    
    # Move previous log files to timestamped folder
    move_previous_logs()
    
    # Create new timestamped log file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    _main_log_file_path = f'./logs/log_last_{timestamp}.log'
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(_main_log_file_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    _logging_initialized = True
    return _main_log_file_path


def setup_logger(prefix, write_to_file=True):
    """
    Get a logger with the specified prefix. Automatically initializes global logging
    if it hasn't been done yet.
    
    Args:
        prefix (str): Prefix to add to all log messages (e.g. module name)
        write_to_file (bool): Whether to write logs to file. If False, only prints to terminal.
    
    Returns:
        logger: Configured logger instance with the specified prefix
    """
    global _logging_initialized, _main_log_file_path
    
    # Initialize logging if not already done
    if not _logging_initialized and write_to_file:
        initialize_logging()
    
    # Create a named logger with the prefix to ensure unique loggers per prefix
    logger = logging.getLogger(prefix)
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates if setup_logging is called multiple times
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Add file handler only if write_to_file is True and logging is initialized
    if write_to_file and _logging_initialized and _main_log_file_path:
        # Add file handler with custom formatter that includes the prefix
        file_handler = logging.FileHandler(_main_log_file_path, mode='a')
        formatter = logging.Formatter(f'%(asctime)s - %(levelname)s - <{prefix}> - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Add console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    colored_formatter = ColoredFormatter(f'%(asctime)s - %(levelname)s - <{prefix}> - %(message)s')
    console_handler.setFormatter(colored_formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    # Prevent propagation to avoid duplicate logs
    logger.propagate = False
    
    return logger


def log_error(logger: logging.Logger, message: str, error: Exception | None = None) -> str:
    """
    Log error details in a consistent format, including local variables from all functions in the call stack.
    Adds a unique ID to the beginning of each error log for easy reference.
    Error message and traceback are logged to both terminal and file.
    Frame variables are logged only to the file.
    
    Args:
        logger (logging.Logger): The logger instance to use
        error_prefix (str): Prefix describing the error context
        error (Exception): The exception object to log
        
    Returns:
        str: A unique ID that can be used to reference this error log
    """
    global errors

    # Generate a unique ID for this error
    error_id = str(uuid.uuid4())  # Using first 8 characters of UUID for brevity
    
    # Log error message and traceback to both terminal and file
    logger.error(f"[ERROR_ID: {error_id}] {message}:")
    logger.error(f"Exception traceback: {traceback.format_exc()}")
    
    # Save full frame information to separate error log file
    error_log_path = f'./logs/errors/log_error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    
    # Create errors directory if it doesn't exist
    os.makedirs('./logs/errors', exist_ok=True)
    
    # Get the current frame
    current_frame = sys._getframe(1)
    
    # Traverse the call stack and save local variables from each frame
    frame = current_frame
    frame_index = 1
    
    with open(error_log_path, 'w', encoding='utf-8') as error_file:
        error_file.write(f"Error ID: {error_id}\n")
        error_file.write(f"Error Message: {message}\n")
        error_file.write(f"Timestamp: {datetime.now().isoformat()}\n")
        error_file.write(f"Exception: {str(error)}\n")
        error_file.write(f"Traceback:\n{traceback.format_exc()}\n")
        error_file.write("="*80 + "\n")
        error_file.write("FRAME_VARIABLES:\n")
        error_file.write("="*80 + "\n\n")
        
        while frame:
            # Get the frame's code context
            code_context = frame.f_code
            filename = code_context.co_filename
            function_name = code_context.co_name
            
            # Get local variables from the frame
            local_vars = frame.f_locals
            
            # Filter out special variables and functions
            filtered_vars = {k: v for k, v in local_vars.items() 
                            if not k.startswith('__') and not callable(v)}
            
            if filtered_vars:
                error_file.write(f"Frame {frame_index}: {filename}:{function_name}\n")
                error_file.write("-" * 60 + "\n")
                
                for var_name, var_value in filtered_vars.items():
                    error_file.write(f"{var_name} = {str(var_value)}\n")
                
                error_file.write("\n")
            
            # Move to the next frame in the call stack
            frame = frame.f_back
            frame_index += 1
        
    notify.notify(f"[ERROR_ID: {error_id}] {message}:\n{type(error).__name__}: {error}", "private")
    
    errors.append({
        'error': error,
        'error_id': error_id,
        'error_message': message,
        'error_traceback': traceback.format_exc(),
    })
    
    return {
        'error_id': error_id,
        'error_message': message,
        'error_traceback': traceback.format_exc()
    }


def log_warning(logger: logging.Logger, message: str) -> None:
    """
    Log a warning message with a unique ID.
    """
    warning_id = str(uuid.uuid4())
    final_message = f"[WARNING_ID: {warning_id}] {message}"
    logger.warning(final_message)
    notify.notify(final_message, "private")