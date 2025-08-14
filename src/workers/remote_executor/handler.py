"""
Remote Executor handler module.

This module provides the main logic for handling remote command execution
and messaging operations.
"""

import json
from typing import Dict, Any
from datetime import datetime
from src.common.exceptions import ConfigurationError, RemoteExecutionError
from src.common.messaging import MessageBroker
from src.common.logger import get_logger
from src.common.db_utils import DatabaseManager
from src.workers.remote_executor.ssh_service import execute


class RemoteExecutorHandler:
    """Handler for Remote Executor operations."""
    
    def __init__(self, config: Dict[str, Any], message_broker: MessageBroker, db_manager: DatabaseManager):
        """
        Initialize Remote Executor Handler.
        
        Args:
            config: Configuration dictionary
            message_broker: Message broker instance for publishing messages
            db_manager: Database manager instance
            
        Raises:
            ConfigurationError: If required configuration is missing
        """
        self.config = config
        self.message_broker = message_broker
        self.db_manager = db_manager
        
        # Use the passed-in db_manager for the logger
        self.logger = get_logger('remote_executor', self.db_manager)
        
        # Validate configuration
        if 'ssh' not in config:
            raise ConfigurationError("Missing ssh configuration section")
        
        ssh_config = config['ssh']
        required_keys = ['host', 'username']
        
        for key in required_keys:
            if key not in ssh_config:
                raise ConfigurationError(f"Missing '{key}' in ssh configuration")
        
        self.ssh_config = ssh_config
        
        # Get conductor queue name from config
        self.conductor_queue = config.get('queues', {}).get('conductor', 'conductor_queue')
        
        # Get execution_failed command from config
        self.execution_failed_cmd = config.get('remote_executor', {}).get('commands', {}).get('execution_failed', 'execution_failed')
        
        # Get remote executor queue name from config
        self.remote_executor_queue = config.get('queues', {}).get('remote_executor', 'remote_executor_queue')
        
        self.logger.info(f"Remote Executor initialized - Target: {ssh_config['host']}")
    
    def _validate_message(self, message: Dict[str, Any], correlation_id: str) -> bool:
        """
        Validate incoming message format and content.
        
        Args:
            message: Message to validate
            correlation_id: Correlation ID for error reporting
            
        Returns:
            bool: True if message is valid, False otherwise
        """
        try:
            # Check if message has required structure
            if not isinstance(message, dict):
                raise ValueError("Message must be a dictionary")
            
            # Check for required fields
            command_type = message.get('command')
            if not command_type:
                raise ValueError("Missing 'command' field in message")
            
            if command_type != 'execute_command':
                raise ValueError(f"Unsupported command type: {command_type}")
            
            payload = message.get('payload')
            if not isinstance(payload, dict):
                raise ValueError("Missing or invalid 'payload' field in message")
            
            # Validate payload content
            command = payload.get('command')
            if not command or not isinstance(command, str):
                raise ValueError("Missing or invalid 'command' field in payload")
            
            case_id = payload.get('case_id')
            if not case_id or not isinstance(case_id, str):
                raise ValueError("Missing or invalid 'case_id' field in payload")
            
            return True
            
        except (ValueError, TypeError, KeyError) as e:
            self.logger.error(f"Message validation failed (correlation_id: {correlation_id}): {e}")
            
            # Send error response to conductor queue for malformed messages
            try:
                self.message_broker.publish(
                    queue_name=self.conductor_queue,
                    command='malformed_message',
                    payload={
                        'error': str(e),
                        'correlation_id': correlation_id,
                        'timestamp': datetime.utcnow().isoformat(),
                        'original_message': str(message)[:500]  # Limit size to prevent issues
                    },
                    correlation_id=correlation_id
                )
            except Exception as pub_e:
                self.logger.error(f"Failed to publish malformed message error (correlation_id: {correlation_id}): {pub_e}")
            
            return False
    
    def on_message_received(self, message: Dict[str, Any], correlation_id: str):
        """
        Handle received message for remote command execution with validation.
        
        Args:
            message: Received message containing command and payload
            correlation_id: Correlation ID for tracing
        """
        # Validate incoming message first
        if not self._validate_message(message, correlation_id):
            return  # Validation method already handles error reporting
        
        try:
            payload = message.get('payload', {})
            command = payload.get('command')
            case_id = payload.get('case_id')
            
            self.logger.info(f"Executing command for case {case_id}: {command}")
            
            try:
                # Execute command via SSH
                result = execute(command, self.ssh_config, self.db_manager)
                
                # Publish success message
                success_cmd = self.config.get('remote_executor', {}).get('commands', {}).get('execution_succeeded', 'execution_succeeded')
                self.message_broker.publish(
                    queue_name=self.conductor_queue,
                    command=success_cmd,
                    payload={
                        'case_id': case_id,
                        'stdout': result['stdout']
                    },
                    correlation_id=correlation_id
                )
                
                self.logger.info(f"Command execution succeeded for case {case_id}")
                
            except RemoteExecutionError as e:
                # Publish failure message
                self.message_broker.publish(
                    queue_name=self.conductor_queue,
                    command=self.execution_failed_cmd,
                    payload={
                        'case_id': case_id,
                        'error': str(e)
                    },
                    correlation_id=correlation_id
                )
                
                self.logger.error(f"Command execution failed for case {case_id}: {e}")
                
        except (ConfigurationError, RemoteExecutionError) as e:
            self.logger.error(f"Remote execution error handling message: {e}")
            # Publish failure message with correlation_id parameter
            self._publish_failure_message(str(e), correlation_id, payload)
        except Exception as e:
            self.logger.error(f"Unexpected error handling message: {e}")
            self._publish_failure_message(f"Unexpected error: {str(e)}", correlation_id, payload)
    
    def run(self):
        """
        Start listening for messages.
        
        This method starts the message broker consumer loop to process
        incoming execute_command messages.
        """
        self.logger.info("Starting Remote Executor message consumer")
        
        try:
            self.message_broker.consume(
                queue_name=self.remote_executor_queue,
                callback=self.on_message_received
            )
        except KeyboardInterrupt:
            self.logger.info("Remote Executor stopped by user")
        except (ConfigurationError, RemoteExecutionError) as e:
            self.logger.error(f"Remote execution error in Remote Executor: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error in Remote Executor: {e}")
            raise
    
    def _publish_failure_message(self, error_message: str, correlation_id: str, payload: Dict[str, Any]):
        """Publish failure message to the messaging system.
        
        Args:
            error_message: Error message to publish
            correlation_id: Correlation ID for tracing
            payload: The original payload that caused the failure
        """
        try:
            failure_payload = {
                'status': 'failed',
                'error': error_message,
                'timestamp': datetime.utcnow().isoformat(),
                'original_payload': payload
            }
            self.message_broker.publish(
                queue_name=self.conductor_queue,
                command=self.execution_failed_cmd,
                payload=failure_payload,
                correlation_id=correlation_id
            )
        except Exception as e:
            self.logger.error(f"Failed to publish failure message: {e}")