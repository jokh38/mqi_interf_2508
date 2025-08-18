"""
Centralized logging setup for the MQI Communicator system.

This module provides a single function to configure logging for the entire
application, including automatic correlation ID injection using contextvars.
"""

import logging
import contextvars
from typing import Optional

from src.common.db_utils import DatabaseManager
from src.common.logger import DatabaseLogHandler

# 1. Define the context variable for the correlation ID.
# This makes the correlation_id available globally within a given asynchronous context.
correlation_id_var = contextvars.ContextVar('correlation_id', default=None)


class ContextVarFilter(logging.Filter):
    """
    A logging filter that injects the correlation_id from a context variable.
    """
    def filter(self, record):
        """
        Adds the correlation_id from the context variable to the log record.
        """
        record.correlation_id = correlation_id_var.get()
        return True


def setup_logging(level: str = 'INFO', db_manager: Optional[DatabaseManager] = None) -> None:
    """
    Configures the root logger for the application.

    This function should be called once at the application's entry point.
    It sets up handlers for console and database logging and adds a filter
    to automatically include the correlation_id in all log records.

    Args:
        level (str): The minimum logging level to capture (e.g., 'INFO', 'DEBUG').
        db_manager (Optional[DatabaseManager]): An instance of the database manager
            to enable logging to the database.
    """
    root_logger = logging.getLogger()

    # Clear any existing handlers to avoid duplicate logs
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.setLevel(level.upper())

    # Add the context variable filter to all handlers
    context_filter = ContextVarFilter()
    root_logger.addFilter(context_filter)

    # 1. Console Handler
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S %z'
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. Database Handler (if db_manager is provided)
    if db_manager:
        try:
            db_handler = DatabaseLogHandler(db_manager)
            db_handler.setLevel(logging.INFO)  # Log INFO and above to DB
            root_logger.addHandler(db_handler)
            root_logger.info("Database logging has been enabled.")
        except Exception as e:
            root_logger.error(f"Failed to initialize database logging: {e}", exc_info=True)
    else:
        root_logger.warning("Database manager not provided. Database logging is disabled.")
