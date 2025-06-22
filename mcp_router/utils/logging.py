"""Logging configuration for MCP Router."""

import logging
import logging.config
import sys
from typing import Dict, Any
from pathlib import Path

import structlog
from pythonjsonlogger import jsonlogger

from mcp_router.config import Settings


def setup_logging(settings: Settings) -> None:
    """Setup application logging configuration."""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if not settings.is_development 
            else structlog.dev.ConsoleRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Logging configuration
    log_level = "DEBUG" if settings.debug else "INFO"
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Console handler
    console_handler = {
        "class": "logging.StreamHandler",
        "stream": sys.stdout,
        "formatter": "console"
    }
    
    # File handler
    log_file = settings.log_dir / "mcp_router.log"
    file_handler = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": str(log_file),
        "maxBytes": 10_000_000,  # 10MB
        "backupCount": 5,
        "formatter": "json" if not settings.is_development else "detailed"
    }
    
    # Error file handler
    error_log_file = settings.log_dir / "mcp_router_errors.log"
    error_handler = {
        "class": "logging.handlers.RotatingFileHandler", 
        "filename": str(error_log_file),
        "maxBytes": 10_000_000,  # 10MB
        "backupCount": 5,
        "level": "ERROR",
        "formatter": "json"
    }
    
    # Formatters
    formatters = {
        "console": {
            "format": log_format
        },
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        },
        "json": {
            "()": jsonlogger.JsonFormatter,
            "format": "%(asctime)s %(name)s %(levelname)s %(funcName)s %(lineno)d %(message)s"
        }
    }
    
    # Loggers configuration
    loggers = {
        "": {  # Root logger
            "level": log_level,
            "handlers": ["console", "file", "error"]
        },
        "mcp_router": {
            "level": log_level,
            "handlers": ["console", "file", "error"],
            "propagate": False
        },
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False
        },
        "uvicorn.access": {
            "level": "INFO",
            "handlers": ["file"],
            "propagate": False
        },
        "httpx": {
            "level": "WARNING",
            "handlers": ["file"],
            "propagate": False
        },
        "docker": {
            "level": "WARNING", 
            "handlers": ["file"],
            "propagate": False
        }
    }
    
    # Complete logging configuration
    config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": {
            "console": console_handler,
            "file": file_handler,
            "error": error_handler
        },
        "loggers": loggers
    }
    
    # Apply configuration
    logging.config.dictConfig(config)
    
    # Set up application logger
    logger = logging.getLogger("mcp_router")
    logger.info("Logging configured", extra={
        "level": log_level,
        "log_file": str(log_file),
        "error_file": str(error_log_file),
        "development": settings.is_development
    })


class StructuredLogger:
    """Structured logger for consistent application logging."""
    
    def __init__(self, name: str):
        self.logger = structlog.get_logger(name)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs) -> None:
        """Log critical message."""
        self.logger.critical(message, **kwargs)
    
    def exception(self, message: str, **kwargs) -> None:
        """Log exception with traceback."""
        self.logger.exception(message, **kwargs)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name) 