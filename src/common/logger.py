"""
Structured logger for MQI Communicator system.
"""

import logging
from datetime import datetime
from typing import Optional
from .db_utils import DatabaseManager


class DatabaseLogHandler(logging.Handler):
    """Custom log handler that writes to database."""
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
    
    def emit(self, record):
        """Write log record to database with retry on lock."""
        import time
        import sqlite3
        
        max_retries = 3
        retry_delay = 0.1
        
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.format(record)

        for attempt in range(max_retries):
            try:
                timestamp = datetime.now().isoformat()
                correlation_id = getattr(record, 'correlation_id', None)
                
                with self.db_manager.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO logs (timestamp, component, level, correlation_id, message) 
                        VALUES (?, ?, ?, ?, ?)
                    """, (timestamp, record.name, record.levelname, correlation_id, message))
                    cursor.connection.commit()  # Explicit commit for logging
                return  # Success, exit retry loop
                
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                    continue
                else:
                    # Final attempt failed or different error
                    print(f"Database OperationalError: {e}")
                    self.handleError(record)
                    return
            except Exception as e:
                print(f"Unexpected error in DatabaseLogHandler: {e}")
                import traceback
                traceback.print_exc()
                self.handleError(record)
                return


def get_logger(name: str, db_manager: Optional[DatabaseManager] = None) -> logging.Logger:
    """
    Get configured logger instance.
    
    Args:
        name: Logger name (typically module name)
        db_manager: Database manager for structured logging
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S %z'
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Database handler if available (optional, with fallback)
        if db_manager:
            try:
                db_handler = DatabaseLogHandler(db_manager)
                logger.addHandler(db_handler)
            except Exception as e:
                # If database logging fails, continue with console logging only
                console_handler.setLevel(logging.DEBUG)  # Increase console logging
                logger.warning(f"Database logging unavailable, using console only: {e}")
    
    return logger


class CorrelationFilter(logging.Filter):
    """Filter to add correlation_id to log records."""
    
    def __init__(self, correlation_id: str):
        super().__init__()
        self.correlation_id = correlation_id
    
    def filter(self, record):
        record.correlation_id = self.correlation_id
        return True