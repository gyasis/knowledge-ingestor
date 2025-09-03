"""
Logging utilities for the Knowledge Ingestor system.

This module provides centralized logging configuration with support for
colored output, file logging, and structured logging formats.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import datetime
import os

try:
    import colorlog
    COLORLOG_AVAILABLE = True
except ImportError:
    COLORLOG_AVAILABLE = False

from ..core.config import get_config, LogLevel


class StructuredFormatter(logging.Formatter):
    """Custom formatter that adds structured information to log records."""
    
    def __init__(self, fmt=None, datefmt=None, style='%', add_structured=True):
        super().__init__(fmt, datefmt, style)
        self.add_structured = add_structured
    
    def format(self, record):
        # Add structured information
        if self.add_structured:
            # Add module and function info
            if not hasattr(record, 'module'):
                record.module = record.name.split('.')[-1]
            
            # Add timestamp in ISO format
            record.isotime = datetime.datetime.fromtimestamp(record.created).isoformat()
            
            # Add process/thread info if not present
            if not hasattr(record, 'process_name'):
                record.process_name = f"Process-{record.process}"
            if not hasattr(record, 'thread_name'):
                record.thread_name = f"Thread-{record.thread}"
        
        return super().format(record)


def setup_logging(config: Optional[Dict[str, Any]] = None) -> None:
    """
    Setup logging configuration for the Knowledge Ingestor system.
    
    Args:
        config: Optional logging configuration override
    """
    # Get configuration
    if config is None:
        app_config = get_config()
        log_config = app_config.logging.dict()
    else:
        log_config = config
    
    # Extract configuration values
    level = log_config.get('level', 'INFO')
    log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_enabled = log_config.get('file_enabled', True)
    file_path = log_config.get('file_path', './logs')
    file_max_size = log_config.get('file_max_size', 10_000_000)  # 10MB
    file_backup_count = log_config.get('file_backup_count', 5)
    console_enabled = log_config.get('console_enabled', True)
    colored_output = log_config.get('colored_output', True)
    
    # Convert string level to logging constant
    if isinstance(level, str):
        numeric_level = getattr(logging, level.upper(), logging.INFO)
    else:
        numeric_level = level
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Setup console handler
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        
        if COLORLOG_AVAILABLE and colored_output:
            # Use colorlog for colored output
            color_formatter = colorlog.ColoredFormatter(
                '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                log_colors={
                    'DEBUG': 'cyan',
                    'INFO': 'green', 
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red,bg_white',
                },
                secondary_log_colors={}
            )
            console_handler.setFormatter(color_formatter)
        else:
            # Use standard formatter
            console_formatter = StructuredFormatter(log_format)
            console_handler.setFormatter(console_formatter)
        
        root_logger.addHandler(console_handler)
    
    # Setup file handler
    if file_enabled and file_path:
        # Create logs directory if it doesn't exist
        log_dir = Path(file_path)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = log_dir / f"knowledge_ingestor_{timestamp}.log"
        
        # Setup rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_filename,
            maxBytes=file_max_size,
            backupCount=file_backup_count
        )
        file_handler.setLevel(numeric_level)
        
        # Use structured formatter for file output
        file_formatter = StructuredFormatter(
            '%(isotime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        
        root_logger.addHandler(file_handler)
        
        # Log the log file location
        root_logger.info(f"Logging to file: {log_filename}")
    
    # Suppress verbose third-party logging
    _suppress_third_party_logging()
    
    # Log configuration info
    root_logger.info(f"Logging configured - Level: {level}, Console: {console_enabled}, File: {file_enabled}")


def _suppress_third_party_logging():
    """Suppress verbose logging from third-party libraries."""
    # Suppress common noisy loggers
    noisy_loggers = [
        'urllib3.connectionpool',
        'requests.packages.urllib3.connectionpool', 
        'asyncio',
        'httpx',
        'openai._base_client',
        'deeplake',
        'newspaper',
        'crawl4ai'
    ]
    
    for logger_name in noisy_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)
    
    # Set specific environment variables to reduce noise
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    os.environ.setdefault("OPENAI_LOG_LEVEL", "ERROR") 
    os.environ.setdefault("GUIDANCE_LOG_LEVEL", "ERROR")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name (typically module name)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    return logging.getLogger(name)


def get_file_logger(
    name: str, 
    log_file: str, 
    level: str = 'INFO',
    format_str: Optional[str] = None
) -> logging.Logger:
    """
    Create a dedicated file logger for specific components.
    
    Args:
        name: Logger name
        log_file: Path to log file
        level: Logging level
        format_str: Custom format string
        
    Returns:
        logging.Logger: Configured file logger
    """
    logger = logging.getLogger(name)
    
    # Don't add handlers if they already exist
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, level.upper()))
    
    # Create file handler
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(getattr(logging, level.upper()))
    
    # Set format
    if format_str is None:
        format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    formatter = StructuredFormatter(format_str)
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    
    # Prevent propagation to avoid duplicate logs
    logger.propagate = False
    
    return logger


class LogContext:
    """Context manager for temporary logging configuration."""
    
    def __init__(self, logger: logging.Logger, level: str):
        self.logger = logger
        self.new_level = getattr(logging, level.upper())
        self.old_level = logger.level
    
    def __enter__(self):
        self.logger.setLevel(self.new_level)
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.setLevel(self.old_level)


def log_with_level(logger: logging.Logger, level: str):
    """
    Create a context manager for temporary log level changes.
    
    Args:
        logger: Logger to modify
        level: Temporary log level
        
    Returns:
        LogContext: Context manager
        
    Usage:
        with log_with_level(logger, 'DEBUG'):
            logger.debug("This will be logged even if default level is INFO")
    """
    return LogContext(logger, level)


class PerformanceTimer:
    """Context manager for performance timing with automatic logging."""
    
    def __init__(self, logger: logging.Logger, operation: str, level: str = 'INFO'):
        self.logger = logger
        self.operation = operation
        self.level = getattr(logging, level.upper())
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.datetime.now()
        self.logger.log(self.level, f"Starting {self.operation}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = datetime.datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.log(self.level, f"Completed {self.operation} in {duration:.2f} seconds")
        else:
            self.logger.error(f"Failed {self.operation} after {duration:.2f} seconds: {exc_val}")


def log_performance(logger: logging.Logger, operation: str, level: str = 'INFO'):
    """
    Create a performance timing context manager.
    
    Args:
        logger: Logger to use
        operation: Description of the operation
        level: Log level for timing messages
        
    Returns:
        PerformanceTimer: Context manager
        
    Usage:
        with log_performance(logger, "document processing"):
            # Your code here
            process_document()
    """
    return PerformanceTimer(logger, operation, level)


# Module-level initialization
_logging_configured = False


def ensure_logging_configured():
    """Ensure logging is configured at least once."""
    global _logging_configured
    if not _logging_configured:
        setup_logging()
        _logging_configured = True