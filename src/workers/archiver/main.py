"""
Archiver main entry point.

This module provides the main entry point for running the Archiver worker
as a message-driven service.
"""

import sys
import os
from src.common.config_loader import load_config
from src.common.messaging import MessageQueue
from src.common.logger import get_logger
from src.common.db_utils import DatabaseManager
from src.common.exceptions import ConfigurationError
from src.workers.archiver.handler import ArchiverHandler


def main(config_path: str):
    """Main entry point for Archiver worker."""
    message_queue = None
    db_manager = None
    logger = None  # Initialize logger to None for broader scope in finally
    
    try:
        # Load configuration from the provided path
        config = load_config(config_path)
        
        # Initialize DatabaseManager
        db_path = config.get('database', {}).get('path')
        if not db_path:
            raise ConfigurationError("Database path not found in configuration.")
        db_manager = DatabaseManager(db_path)
        
        # Initialize a DB-aware logger
        logger = get_logger('archiver', db_manager=db_manager)
        
        # Initialize message queue
        rabbitmq_params = config.get('rabbitmq')
        if not rabbitmq_params:
            raise ConfigurationError("RabbitMQ configuration not found.")
        message_queue = MessageQueue(rabbitmq_params, config, db_manager)
        
        # Initialize and run handler
        handler = ArchiverHandler(config, message_queue, db_manager)
        handler.run()
        
    except ConfigurationError as e:
        if logger:
            logger.error(f"Configuration error: {e}")
        else:
            print(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        if logger:
            logger.info("Archiver terminated by user")
        else:
            print("Archiver terminated by user")
    except Exception as e:
        if logger:
            logger.error(f"Unexpected error: {e}", exc_info=True)
        else:
            print(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        if message_queue is not None:
            try:
                message_queue.close()
            except Exception as e:
                if logger:
                    logger.error(f"Error closing message queue during cleanup: {e}")
        
        if db_manager is not None:
            try:
                db_manager.close()
            except Exception as e:
                if logger:
                    logger.error(f"Error closing database manager during cleanup: {e}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python -m src.workers.archiver.main <config_path>")
        sys.exit(1)
    main(sys.argv[1])