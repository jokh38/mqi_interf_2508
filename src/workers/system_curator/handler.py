"""
System Curator message handler.
Handles system_monitor messages by collecting GPU metrics and updating database.
"""

from typing import Dict, Any
from src.common.messaging import MessageBroker
from src.common.logger import get_logger
from src.common.db_utils import DatabaseManager
from src.common.exceptions import ConfigurationError, RemoteExecutionError, DatabaseError
from src.workers.system_curator.monitor_service import fetch_gpu_metrics
from src.workers.system_curator.db_service import update_resource_status


class SystemCuratorHandler:
    """Handler for system curator messages."""
    
    def __init__(self, config: Dict[str, Any], message_broker: MessageBroker, db_manager: DatabaseManager):
        """
        Initialize system curator handler.
        
        Args:
            config: Configuration dictionary
            message_broker: Message broker instance
            db_manager: Database manager instance
            
        Raises:
            ConfigurationError: If required configuration is missing or invalid
        """
        self.config = config
        self.message_broker = message_broker
        self.db_manager = db_manager
        
        # Use the passed-in db_manager for the logger
        self.logger = get_logger('system_curator', self.db_manager)
        
        self._validate_config()

        self.system_curator_queue = config.get('queues', {}).get('system_curator', 'system_curator_queue')
        
        self.logger.info("System Curator Handler initialized")
    
    def _validate_config(self) -> None:
        """
        Validate required configuration parameters.
        
        Raises:
            ConfigurationError: If required configuration is missing
        """
        # Only validate what this handler directly needs
        # SSH and curator configuration is validated by the services that use them
        if 'database' not in self.config:
            raise ConfigurationError("Missing required configuration section: database")
        
        database_config = self.config['database']
        if 'path' not in database_config:
            raise ConfigurationError("Missing required database configuration: path")
    
    def on_message_received(self, message_data: Dict[str, Any], correlation_id: str) -> None:
        """
        Handle received messages.
        
        Args:
            message_data: Message data containing command and payload
            correlation_id: Correlation ID for tracing
        """
        command = message_data.get('command')
        payload = message_data.get('payload', {})
        
        self.logger.info(f"Received command '{command}' with correlation_id: {correlation_id}")
        
        try:
            if command == 'system_monitor':
                self._handle_system_monitor(payload, correlation_id)
            else:
                self.logger.warning(f"Unknown command received: {command}")
                
        except Exception as e:
            self.logger.error(f"Error processing command '{command}': {e}", 
                            extra={'correlation_id': correlation_id})
    
    def _handle_system_monitor(self, payload: Dict[str, Any], correlation_id: str) -> None:
        """
        Handle system_monitor command.
        Execute one monitoring cycle - fetches GPU metrics from remote system and updates database.
        
        Args:
            payload: Command payload (currently unused)
            correlation_id: Correlation ID for tracing
        """
        try:
            # Fetch GPU metrics from remote system
            self.logger.debug("Starting GPU metrics collection", 
                            extra={'correlation_id': correlation_id})
            gpu_metrics = fetch_gpu_metrics(self.config, self.db_manager)
            
            # Update database with collected metrics
            self.logger.debug(f"Updating database with {len(gpu_metrics)} GPU metrics", 
                            extra={'correlation_id': correlation_id})
            update_resource_status(self.db_manager, gpu_metrics)
            
            self.logger.info(f"Monitor cycle completed successfully, updated {len(gpu_metrics)} GPUs", 
                           extra={'correlation_id': correlation_id})
            
        except RemoteExecutionError as e:
            self.logger.error(f"Failed to collect GPU metrics: {e}", 
                            extra={'correlation_id': correlation_id})
            raise
        except DatabaseError as e:
            self.logger.error(f"Failed to update database: {e}", 
                            extra={'correlation_id': correlation_id})
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during monitor cycle: {e}", 
                            extra={'correlation_id': correlation_id})
            raise
    
    def run(self):
        """
        Start listening for messages.
        
        This method starts the message broker consumer loop to process
        incoming system_monitor messages.
        """
        self.logger.info("Starting System Curator message consumer")
        
        try:
            self.message_broker.consume(
                queue_name=self.system_curator_queue,
                callback=self.on_message_received
            )
        except KeyboardInterrupt:
            self.logger.info("System Curator stopped by user")
        except (ConfigurationError, RemoteExecutionError, DatabaseError) as e:
            self.logger.error(f"System Curator error: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error in System Curator: {e}")
            raise