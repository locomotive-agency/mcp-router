"""Centralized logging configuration using loguru.

This module configures loguru to intercept all Python logging and standardize
the format across the application, including uvicorn and third-party libraries.
"""

import logging
import sys
import warnings

from loguru import logger

from mcp_anywhere.config import Config


class InterceptHandler(logging.Handler):
    """Handler to intercept standard logging and redirect to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to loguru."""
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(
    log_level: str | None = None,
    log_format: str | None = None,
    log_file: str | None = None,
    json_logs: bool = False,
) -> None:
    """Configure logging for the entire application using loguru."""
    # Remove default loguru handler
    logger.remove()

    # Set defaults from config
    log_level = log_level or Config.LOG_LEVEL

    # Define log format
    if json_logs:
        # JSON format for production/parsing
        format_string = (
            '{"time":"{time:YYYY-MM-DD HH:mm:ss.SSS}", '
            '"level":"{level}", '
            '"logger":"{name}", '
            '"function":"{function}", '
            '"line":{line}, '
            '"message":"{message}", '
            '"extra":{extra}}'
        )
    else:
        # Human-readable format for development
        if log_format:
            format_string = log_format
        else:
            format_string = (
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            )

    # Add stderr handler
    logger.add(
        sys.stderr,
        format=format_string,
        level=log_level.upper(),
        colorize=not json_logs,
        serialize=json_logs,
        backtrace=True,
        diagnose=True,
        enqueue=True,  # Thread-safe by default
    )

    # Add file handler if specified
    if log_file:
        logger.add(
            log_file,
            format=format_string,
            level=log_level.upper(),
            rotation="100 MB",
            retention="1 week",
            compression="zip",
            serialize=json_logs,
            backtrace=True,
            diagnose=True,
            enqueue=True,
        )

    # Intercept standard logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Intercept specific loggers that might have their own handlers
    for logger_name in [
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "fastapi",
        "sqlalchemy",
        "httpx",
        "anthropic",
        "docker",
        "asyncio",
        "mcp",
        "fastmcp",
        "llm_sandbox",
    ]:
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]
        logging_logger.propagate = False

    # Suppress specific warnings
    suppress_deprecation_warnings()

    logger.info(
        "Logging configured",
        level=log_level,
        json_logs=json_logs,
        log_file=log_file,
    )


def suppress_deprecation_warnings() -> None:
    """Suppress known deprecation warnings that we can't fix yet."""
    # Suppress websockets deprecation warnings from uvicorn
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module="websockets.legacy",
    )
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module="websockets.server",
    )
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module="uvicorn.protocols.websockets.websockets_impl",
    )

    # Log that we're suppressing these warnings
    logger.debug("Suppressing websockets deprecation warnings until uvicorn updates to new API")


def get_logger(name: str):
    """Get a logger instance with the given name."""
    return logger.bind(name=name)
