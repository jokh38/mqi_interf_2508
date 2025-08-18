"""
Structured logger for MQI Communicator system.
"""

import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .db_utils import DatabaseManager


class DatabaseLogHandler(logging.Handler):
    """Custom log handler that writes log records to an SQLite database."""

    def __init__(self, db_manager: "DatabaseManager"):
        super().__init__()
        self.db_manager = db_manager

    def emit(self, record: logging.LogRecord):
        """
        Write log record to the database.

        Includes retry logic with exponential backoff for locked databases.
        """
        max_retries = 3
        retry_delay = 0.1
        
        # The full message, including traceback if present
        message = self.format(record)

        for attempt in range(max_retries):
            try:
                timestamp = datetime.fromtimestamp(record.created).astimezone().isoformat()
                correlation_id = getattr(record, 'correlation_id', None)

                with self.db_manager.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO logs (timestamp, component, level, correlation_id, message)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (timestamp, record.name, record.levelname, correlation_id, message)
                    )
                return  # Success

            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                else:
                    self.handleError(record)
                    return
            except Exception:
                self.handleError(record)
                return


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Configuration is handled centrally by setup_logging(). This function
    is just a convenient wrapper around logging.getLogger().

    Args:
        name: The name for the logger (typically __name__).

    Returns:
        A logger instance.
    """
    return logging.getLogger(name)