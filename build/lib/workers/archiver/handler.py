"""
Archiver message handler.
Handles archive_data messages by performing archiving and database backup operations.
"""

from typing import Dict, Any
from src.common.messaging import MessageBroker
from src.common.logger import get_logger
from src.common.db_utils import DatabaseManager
from src.common.exceptions import ConfigurationError, DatabaseError
from src.workers.archiver.archiver_service import archive_old_data, backup_database


class ArchiverHandler:
    """Handler for archiver messages."""

    def __init__(self, config: Dict[str, Any], message_broker: MessageBroker, db_manager: DatabaseManager):
        """
        Initialize archiver handler.

        Args:
            config: Configuration dictionary
            message_broker: Message broker instance
            db_manager: Database manager instance

        Raises:
            ConfigurationError: If required configuration is missing
        """
        self.config = config
        self.message_broker = message_broker
        self.db_manager = db_manager

        # Use the passed-in db_manager for the logger
        self.logger = get_logger('archiver', self.db_manager)

        self._validate_config(config)

        self.retention_days = config['archiver']['retention_days']
        self.backup_path = config['archiver']['backup_path']

        self.logger.info(f"Archiver Handler initialized - "
                        f"Retention: {self.retention_days} days, Backup: {self.backup_path}")

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate required configuration parameters.

        Args:
            config: Configuration dictionary

        Raises:
            ConfigurationError: If required configuration is missing
        """
        if 'database' not in config or 'path' not in config['database']:
            raise ConfigurationError("Database path configuration is required")

        if 'archiver' not in config:
            raise ConfigurationError("Archiver configuration is required")

        archiver_config = config['archiver']
        required_keys = ['retention_days', 'backup_path']

        for key in required_keys:
            if key not in archiver_config:
                raise ConfigurationError(f"Archiver configuration missing required key: {key}")

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
            if command == 'archive_data':
                self._handle_archive_data(payload, correlation_id)
            else:
                self.logger.warning(f"Unknown command received: {command}")

        except Exception as e:
            self.logger.error(f"Error processing command '{command}': {e}",
                            extra={'correlation_id': correlation_id})

    def _handle_archive_data(self, payload: Dict[str, Any], correlation_id: str) -> None:
        """
        Handle archive_data command.

        Args:
            payload: Command payload (currently unused, uses config values)
            correlation_id: Correlation ID for tracing
        """
        try:
            self.logger.info("Starting scheduled archive job",
                           extra={'correlation_id': correlation_id})

            # Archive old data
            self.logger.info(f"Archiving old data with retention period of {self.retention_days} days",
                           extra={'correlation_id': correlation_id})
            archive_old_data(self.db_manager, self.retention_days)

            # Backup database
            self.logger.info(f"Creating database backup to {self.backup_path}",
                           extra={'correlation_id': correlation_id})
            backup_database(self.db_manager, self.backup_path)

            self.logger.info("Archive job completed successfully",
                           extra={'correlation_id': correlation_id})

        except DatabaseError as e:
            self.logger.error(f"Database error during archiving: {e}",
                            extra={'correlation_id': correlation_id})
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during archiving: {e}",
                            extra={'correlation_id': correlation_id})
            raise

    def run(self):
        """
        Start listening for messages.

        This method starts the message broker consumer loop to process
        incoming archive_data messages.
        """
        self.logger.info("Starting Archiver message consumer")

        try:
            queue_name = self.config.get('queues', {}).get('archiver', 'archiver_queue')
            self.message_broker.consume(
                queue_name=queue_name,
                callback=self.on_message_received
            )
        except KeyboardInterrupt:
            self.logger.info("Archiver stopped by user")
        except (ConfigurationError, DatabaseError) as e:
            self.logger.error(f"Archiver error: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error in Archiver: {e}")
            raise