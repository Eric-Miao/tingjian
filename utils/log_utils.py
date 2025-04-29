import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from functools import wraps
import inspect
import asyncio
from datetime import datetime


# For colored output
try:
    import colorlog
except ImportError:
    print("Warning: colorlog not installed. Install it with 'pip install colorlog' for colored logs.")
    colorlog = None


class LogUtils:
    DEFAULT_FORMAT = "%(name)s: %(asctime)s | %(levelname)s | %(filename)s:%(lineno)s | %(process)d >>> %(message)s"
    DEFAULT_LOG_DIR = "logs"
    LOG_FILE = f"{os.path.splitext(os.path.basename(sys.argv[0]))[0]}_{datetime.now().strftime('%Y-%m-%d')}"
    DEFAULT_LOG_FILE = f"{LOG_FILE}.log"
    DEFAULT_ERROR_LOG_FILE = f"{LOG_FILE}_error.log"
    DEFAULT_CRITICAL_LOG_FILE = f"{LOG_FILE}_critical.log"
    DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5MB
    DEFAULT_BACKUP_COUNT = 3

    @classmethod
    def setup_logger(
        cls,
        logger_name=None,
        log_dir=DEFAULT_LOG_DIR,
        log_file=DEFAULT_LOG_FILE,
        error_log_file=DEFAULT_ERROR_LOG_FILE,
        critical_log_file=DEFAULT_CRITICAL_LOG_FILE,
        level=logging.INFO,
        console_level=None,
        file_level=None,
        format_str=DEFAULT_FORMAT,
        use_color=True,
        max_bytes=DEFAULT_MAX_BYTES,
        backup_count=DEFAULT_BACKUP_COUNT,
    ):
        """
        Setup a logger with console and file handlers.
        
        Args:
            logger_name: Logger name (default: calling module's __name__)
            log_dir: Directory to store log files
            log_file: Main log file name
            error_log_file: Error log file name
            critical_log_file: Critical log file name
            level: Overall logger level
            console_level: Console handler level (defaults to overall level)
            file_level: File handler level (defaults to overall level)
            format_str: Log format string
            use_color: Whether to use colored logs in console
            max_bytes: Maximum size in bytes for each log file
            backup_count: Number of backup files to keep
            
        Returns:
            logger: Configured logger instance
        """
        # Get the caller's module name if not provided
        if logger_name is None:
            frame = inspect.currentframe().f_back
            module = inspect.getmodule(frame)
            logger_name = module.__name__ if module else "__main__"
        
        # Create logger
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.handlers = []  # Remove any existing handlers
        
        # Set default levels if not specified
        if console_level is None:
            console_level = level
        if file_level is None:
            file_level = level
        
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        
        # Set up colored formatter for console if requested and available
        if use_color and colorlog:
            color_formatter = colorlog.ColoredFormatter(
                "%(log_color)s" + format_str,
                log_colors={
                    'DEBUG': 'cyan',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red,bg_white',
                }
            )
            console_handler.setFormatter(color_formatter)
        else:
            formatter = logging.Formatter(format_str)
            console_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        
        # Create log directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Setup main file handler with rotation
        main_file_handler = RotatingFileHandler(
            os.path.join(log_dir, log_file),
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        main_file_handler.setLevel(file_level)
        main_file_handler.setFormatter(logging.Formatter(format_str))
        logger.addHandler(main_file_handler)
        
        # Setup error file handler with filter
        error_file_handler = RotatingFileHandler(
            os.path.join(log_dir, error_log_file),
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(logging.Formatter(format_str))
        
        # Add a filter to only include ERROR level logs
        class ErrorFilter(logging.Filter):
            def filter(self, record):
                return record.levelno == logging.ERROR
        
        error_file_handler.addFilter(ErrorFilter())
        logger.addHandler(error_file_handler)
        
        # Setup critical file handler
        critical_file_handler = RotatingFileHandler(
            os.path.join(log_dir, critical_log_file),
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        critical_file_handler.setLevel(logging.CRITICAL)
        critical_file_handler.setFormatter(logging.Formatter(format_str))
        logger.addHandler(critical_file_handler)
        
        return logger


def get_logger(name=None, **kwargs):
    """
    Get a logger with the default configuration.
    
    Args:
        name: Logger name (default: calling module's __name__)
        **kwargs: Additional configuration options to pass to setup_logger
        
    Returns:
        logger: Configured logger instance
    """
    if name is None:
        frame = inspect.currentframe().f_back
        module = inspect.getmodule(frame)
        name = module.__name__ if module else "__main__"
    
    # Check if logger already exists and has handlers
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    
    return LogUtils.setup_logger(logger_name=name, **kwargs)

def catch_exceptions(logger=None):
    """
    Decorator to catch exceptions and log them.
    Works with both sync and async functions.
    
    Args:
        logger: Logger instance (default: root logger)
    """
    if logger is None:
        logger = logging.getLogger()
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Exception in {func.__name__}: {str(e)}")
                raise
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Exception in async {func.__name__}: {str(e)}")
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    
    return decorator


def log_execution(logger=None, level=logging.INFO):
    """
    Decorator to log when a function starts and completes execution.
    Works with both sync and async functions.
    
    Args:
        logger: Logger instance (default: root logger)
        level: Logging level to use
    """
    if logger is None:
        logger = logging.getLogger()
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger.log(level, f"Starting execution of {func.__name__}")
            result = func(*args, **kwargs)
            logger.log(level, f"Completed execution of {func.__name__}")
            return result
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger.log(level, f"Starting execution of async {func.__name__}")
            result = await func(*args, **kwargs)
            logger.log(level, f"Completed execution of async {func.__name__}")
            return result
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    
    return decorator