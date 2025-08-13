"""
System Curator main entry point.

This module provides the main entry point for running the System Curator worker
as a message-driven service.
"""

import sys
import os
from src.common.config_loader import load_config, get_project_root
from src.common.messaging import MessageQueue
from src.common.logger import get_logger
from src.common.db_utils import DatabaseManager
from src.common.exceptions import ConfigurationError
from src.workers.system_curator.handler import SystemCuratorHandler


def main():
    """Main entry point for System Curator worker."""
    message_queue = None
    db_manager = None
    
    try:
        # Load configuration
        config_path = os.environ.get('MQI_CONFIG_PATH')
        if config_path and not os.path.isabs(config_path):
            # Make relative paths absolute from project root
            project_root = get_project_root()
            config_path = str(project_root / config_path)
        config = load_config(config_path)
        
        # Initialize DatabaseManager
        db_manager = DatabaseManager(config['database']['path'])
        
        # Initialize a DB-aware logger
        logger = get_logger('system_curator', db_manager)
        
        # Initialize message queue
        rabbitmq_params = config.get('rabbitmq', {
            'url': 'amqp://localhost:5672'
        })
        message_queue = MessageQueue(rabbitmq_params, config, db_manager)
        
        # Initialize and run handler
        handler = SystemCuratorHandler(config, message_queue, db_manager)
        handler.run()
        
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("System Curator terminated by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        if message_queue is not None:
            try:
                message_queue.close()
            except Exception as e:
                if 'logger' in locals():
                    logger.error(f"Error closing message queue during cleanup: {e}")
        
        if db_manager is not None:
            try:
                db_manager.close()
            except Exception as e:
                if 'logger' in locals():
                    logger.error(f"Error closing database manager during cleanup: {e}")


if __name__ == "__main__":
    main()