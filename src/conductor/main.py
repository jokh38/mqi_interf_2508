"""
Main entry point for the Conductor module.

The Conductor orchestrates the entire MQI workflow by:
- Listening for messages from workers
- Managing workflow state transitions
- Coordinating resource allocation
- Handling error recovery
"""

import os
from typing import Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from src.common.config_loader import load_config
from src.common.db_utils import DatabaseManager
from src.common.messaging import MessageQueue
from src.common.exceptions import ConfigurationError
from src.common.logger import get_logger
from .workflow_manager import WorkflowManager


class ConfigWrapper:
    """Wrapper class to provide dict-like access to config with dot notation."""

    def __init__(self, config_dict: Dict[str, Any]):
        self.config = config_dict

    def get(self, key: str, default=None):
        """Get configuration value using dot notation."""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value


class ConductorMain:
    """Main Conductor class that orchestrates the workflow."""

    def __init__(self, config_path: str):
        """
        Initialize the Conductor with configuration.
        
        Args:
            config_path: Path to the configuration file
        """
        config_dict = load_config(config_path)
        self.config = ConfigWrapper(config_dict)
        self._validate_config()

        # Initialize database connection
        self.db_manager = DatabaseManager(self.config.get('database.path'))

        # Initialize workflow manager
        self.workflow_manager = WorkflowManager(self.db_manager, self.config)

        # Initialize message queue (will be set up in start())
        self.message_queue = None
        
        # Initialize scheduler
        self.scheduler = BackgroundScheduler()

        self.logger = get_logger('conductor', self.db_manager)

    def _validate_config(self):
        """Validate required configuration parameters."""
        required_keys = [
            'database.path',
            'workflows.default_qa',
            'remote_commands',
            'conductor.monitor_interval_sec'
        ]

        for key in required_keys:
            if not self.config.get(key):
                raise ConfigurationError(f"Missing required configuration: {key}")

    def start(self):
        """Start the Conductor service."""
        self.logger.info("Starting MQI Conductor...")
        try:
            # Initialize message queue
            mq_config = self.config.get('rabbitmq', {})
            self.message_queue = MessageQueue(mq_config)
            self.message_queue.connect()

            # Set up publisher for workflow manager
            class MessagePublisher:
                def __init__(self, message_queue, config):
                    self.mq = message_queue
                    self.config = config

                def publish(self, command, payload, correlation_id=None):
                    # Route to appropriate queue based on command
                    queue_name = self._get_queue_for_command(command)
                    return self.mq.publish_message(queue_name, command, payload, correlation_id)

                def _get_queue_for_command(self, command):
                    # Use centralized queue configuration
                    queues_config = self.config.get('queues', {})
                    command_queue_map = {
                        'execute_command': queues_config.get('remote_executor', 'remote_executor_queue'),
                        'upload_case': queues_config.get('file_transfer', 'file_transfer_queue'),
                        'download_results': queues_config.get('file_transfer', 'file_transfer_queue'),
                        'case_upload_completed': queues_config.get('conductor', 'conductor_queue'),
                        'results_download_completed': queues_config.get('conductor', 'conductor_queue'),
                        'execution_failed': queues_config.get('conductor', 'conductor_queue'),
                        'execution_succeeded': queues_config.get('conductor', 'conductor_queue'),
                        'download_completed': queues_config.get('conductor', 'conductor_queue'),
                        'system_monitor': queues_config.get('system_curator', 'system_curator_queue')
                    }
                    return command_queue_map.get(command, queues_config.get('conductor', 'conductor_queue'))

            self.workflow_manager.publisher = MessagePublisher(self.message_queue, self.config)
            
            # Schedule system tasks
            self._schedule_system_tasks()

            # Start consuming messages
            conductor_queue_name = self.config.get('queues', {}).get('conductor', 'conductor_queue')
            self.message_queue.consume_messages(conductor_queue_name, self._message_callback)

            self.logger.info("Conductor started successfully")
        except Exception as e:
            self.logger.error(f"Failed to start Conductor: {e}")
            raise

    def stop(self):
        """Stop the Conductor service."""
        self.logger.info("Stopping MQI Conductor...")
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
            if self.message_queue:
                self.message_queue.close()
            self.db_manager.close()
            self.logger.info("Conductor stopped successfully")
        except Exception as e:
            self.logger.error(f"Error stopping Conductor: {e}")
    
    def _schedule_system_tasks(self):
        """Schedule periodic system tasks."""
        monitor_interval = self.config.get('conductor.monitor_interval_sec')
        self.scheduler.add_job(
            self._send_monitor_task,
            'interval',
            seconds=monitor_interval,
            id='system_monitor_task'
        )
        self.scheduler.start()
        self.logger.info(f"Scheduled system monitor task every {monitor_interval} seconds.")

    def _send_monitor_task(self):
        """Send a system monitor task to the message queue."""
        self.logger.info("Sending system monitor task...")
        try:
            if self.workflow_manager.publisher:
                self.workflow_manager.publisher.publish('system_monitor', {})
            else:
                self.logger.error("Publisher not initialized, cannot send monitor task.")
        except Exception as e:
            self.logger.error(f"Failed to send system monitor task: {e}")

    def _message_callback(self, message_data: Dict[str, Any], correlation_id: str):
        """Handle incoming messages from message queue."""
        try:
            command = message_data.get('command')
            payload = message_data.get('payload', {})

            if command is None:
                self.logger.error("Received message without command")
                return

            self.logger.info(f"Received message: {command}, correlation_id: {correlation_id}")

            # Route message to workflow manager
            self.workflow_manager.handle_message(command, payload, correlation_id)

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            # Handle workflow failure if we have case_id
            if 'case_id' in message_data.get('payload', {}):
                self.workflow_manager.handle_workflow_failure(
                    message_data['payload']['case_id'],
                    f"Message processing error: {e}"
                )


if __name__ == "__main__":
    import sys

    config_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("config", "config.default.yaml")

    conductor = ConductorMain(config_path)
    try:
        conductor.start()
    except KeyboardInterrupt:
        conductor.stop()