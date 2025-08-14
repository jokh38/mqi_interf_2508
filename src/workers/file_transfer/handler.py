"""
File Transfer message handler.
"""

import os
import time
import sys
import threading
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from src.common.messaging import MessageBroker
from src.common.logger import get_logger
from src.common.db_utils import DatabaseManager
from src.common.exceptions import NetworkError, DataIntegrityError, ConfigurationError
from src.workers.file_transfer.sftp_service import SftpService


class FileTransferHandler:
    """Handler for file transfer messages."""
    
    def __init__(self, config: Dict[str, Any], message_broker: MessageBroker, db_manager: DatabaseManager):
        """
        Initialize file transfer handler.
        
        Args:
            config: Configuration dictionary
            message_broker: Message broker instance
            db_manager: Database manager instance
        """
        self.config = config
        self.message_broker = message_broker
        self.db_manager = db_manager
        
        # Use the passed-in db_manager for the logger
        self.logger = get_logger('file_transfer', self.db_manager)
        
        # Thread safety lock for file operations
        self._operation_lock = threading.Lock()
        
        # Initialize SFTP service
        sftp_config = config.get('sftp', {})
        if not sftp_config:
            raise ConfigurationError("SFTP configuration not found")
        
        self.sftp_service = SftpService(sftp_config)
        
        # Retry configuration
        self.max_retries = config.get('file_transfer', {}).get('max_retries', 3)
        self.retry_delay = config.get('file_transfer', {}).get('retry_delay_sec', 5)
        
        # Get conductor queue name from config
        self.conductor_queue = config.get('queues', {}).get('conductor', 'conductor_queue')
    
    def _validate_message(self, message_data: Dict[str, Any], correlation_id: str) -> bool:
        """
        Validate incoming message format and content.
        
        Args:
            message_data: Message to validate
            correlation_id: Correlation ID for error reporting
            
        Returns:
            bool: True if message is valid, False otherwise
        """
        try:
            # Check if message has required structure
            if not isinstance(message_data, dict):
                raise ValueError("Message must be a dictionary")
            
            # Check for required fields
            command = message_data.get('command')
            if not command or not isinstance(command, str):
                raise ValueError("Missing or invalid 'command' field in message")
            
            # Validate supported commands
            if command not in ['upload_case', 'download_results']:
                raise ValueError(f"Unsupported command type: {command}")
            
            payload = message_data.get('payload')
            if not isinstance(payload, dict):
                raise ValueError("Missing or invalid 'payload' field in message")
            
            # Validate payload fields based on command
            required_fields = ['local_path', 'remote_path', 'case_id']
            for field in required_fields:
                if not payload.get(field) or not isinstance(payload.get(field), str):
                    raise ValueError(f"Missing or invalid '{field}' field in payload")
            
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
                        'original_message': str(message_data)[:500]  # Limit size to prevent issues
                    },
                    correlation_id=correlation_id
                )
            except Exception as pub_e:
                self.logger.error(f"Failed to publish malformed message error (correlation_id: {correlation_id}): {pub_e}")
            
            return False
    
    def _validate_payload_fields(self, payload: Dict[str, Any], operation: str, correlation_id: str) -> bool:
        """
        Consolidated validation for payload fields common to both upload and download operations.
        
        Args:
            payload: Message payload to validate
            operation: Operation type ('upload' or 'download') for error reporting
            correlation_id: Correlation ID for error reporting
            
        Returns:
            bool: True if payload is valid, False otherwise
        """
        required_fields = ['local_path', 'remote_path', 'case_id']
        
        # Check for missing or invalid fields
        for field in required_fields:
            if not payload.get(field) or not isinstance(payload.get(field), str):
                raise ValueError(f"Missing or invalid '{field}' field in payload")
                
        return True
    
    def on_message_received(self, message_data: Dict[str, Any], correlation_id: str) -> None:
        """
        Handle received messages with enhanced validation and error handling.
        
        Args:
            message_data: Message data containing command and payload
            correlation_id: Correlation ID for tracing
        """
        # Validate incoming message first
        if not self._validate_message(message_data, correlation_id):
            return  # Validation method already handles error reporting
        
        try:
            command = message_data.get('command')
            payload = message_data.get('payload', {})
            
            self.logger.info(f"Received command: {command}", extra={'correlation_id': correlation_id})
            
            if command == 'upload_case':
                self._handle_upload_case(payload, correlation_id)
            elif command == 'download_results':
                self._handle_download_results(payload, correlation_id)
                
        except (NetworkError, DataIntegrityError, ConfigurationError) as e:
            self.logger.error(f"File transfer error handling message: {e}", extra={'correlation_id': correlation_id})
            # Report error to conductor_queue as specified in revision plan
            self._publish_failure_message(
                "file_transfer_failed", 
                {
                    "error": str(e), 
                    "command": message_data.get('command'), 
                    "error_type": type(e).__name__,
                    "timestamp": datetime.utcnow().isoformat(),
                    "correlation_id": correlation_id
                },
                correlation_id
            )
        except Exception as e:
            self.logger.error(f"Unexpected error handling message: {e}", extra={'correlation_id': correlation_id})
            # Report unexpected errors to conductor_queue
            self._publish_failure_message(
                "file_transfer_failed", 
                {
                    "error": f"Unexpected error: {str(e)}", 
                    "command": message_data.get('command'), 
                    "error_type": "UnexpectedError",
                    "timestamp": datetime.utcnow().isoformat(),
                    "correlation_id": correlation_id
                },
                correlation_id
            )
    
    def _handle_upload_case(self, payload: Dict[str, Any], correlation_id: str) -> None:
        """
        Handle case upload request with thread-safe operations.
        
        Args:
            payload: Message payload containing local_path and remote_path
            correlation_id: Correlation ID for tracing
        """
        try:
            # Use consolidated validation
            self._validate_payload_fields(payload, "upload", correlation_id)

            local_path = payload.get('local_path')
            remote_path = payload.get('remote_path')
            case_id = payload.get('case_id')
        except ValueError as e:
            self.logger.error(f"Invalid payload for upload case: {e}", extra={'correlation_id': correlation_id})
            self._publish_failure_message(
                "file_transfer_failed",
                {
                    "error": str(e),
                    "operation": "upload",
                    "payload": payload
                },
                correlation_id
            )
            return
        
        self.logger.info(f"Starting case upload: {case_id} from {local_path} to {remote_path}", extra={'correlation_id': correlation_id})
        
        # Perform upload with thread safety and retry logic
        with self._operation_lock:
            success = self._retry_operation(
                lambda: self._upload_with_verification(local_path, remote_path),
                f"upload case {case_id}"
            )
        
        if success:
            self.logger.info(f"Case upload completed successfully: {case_id}", extra={'correlation_id': correlation_id})
            self._publish_success_message(
                "case_upload_completed",
                {
                    "case_id": case_id,
                    "local_path": local_path,
                    "remote_path": remote_path
                },
                correlation_id
            )
        else:
            self.logger.error(f"Case upload failed after all retries: {case_id}", extra={'correlation_id': correlation_id})
            self._publish_failure_message(
                "file_transfer_failed",
                {
                    "case_id": case_id,
                    "local_path": local_path,
                    "remote_path": remote_path,
                    "operation": "upload"
                },
                correlation_id
            )
    
    def _handle_download_results(self, payload: Dict[str, Any], correlation_id: str) -> None:
        """
        Handle results download request with thread-safe operations.
        
        Args:
            payload: Message payload containing local_path and remote_path
            correlation_id: Correlation ID for tracing
        """
        try:
            # Use consolidated validation
            self._validate_payload_fields(payload, "download", correlation_id)

            local_path = payload.get('local_path')
            remote_path = payload.get('remote_path')
            case_id = payload.get('case_id')
        except ValueError as e:
            self.logger.error(f"Invalid payload for download results: {e}", extra={'correlation_id': correlation_id})
            self._publish_failure_message(
                "file_transfer_failed",
                {
                    "error": str(e),
                    "operation": "download",
                    "payload": payload
                },
                correlation_id
            )
            return
        
        self.logger.info(f"Starting results download: {case_id} from {remote_path} to {local_path}", extra={'correlation_id': correlation_id})
        
        # Perform download with thread safety and retry logic
        with self._operation_lock:
            success = self._retry_operation(
                lambda: self._download_with_verification(remote_path, local_path),
                f"download results {case_id}"
            )
        
        if success:
            self.logger.info(f"Results download completed successfully: {case_id}", extra={'correlation_id': correlation_id})
            self._publish_success_message(
                "results_download_completed",
                {
                    "case_id": case_id,
                    "local_path": local_path,
                    "remote_path": remote_path
                },
                correlation_id
            )
        else:
            self.logger.error(f"Results download failed after all retries: {case_id}", extra={'correlation_id': correlation_id})
            self._publish_failure_message(
                "file_transfer_failed",
                {
                    "case_id": case_id,
                    "local_path": local_path,
                    "remote_path": remote_path,
                    "operation": "download"
                },
                correlation_id
            )
    
    def _upload_with_verification(self, local_path: str, remote_path: str) -> None:
        """
        Upload file/directory and verify integrity with enhanced error handling.
        
        Args:
            local_path: Local source path
            remote_path: Remote destination path
            
        Raises:
            NetworkError: If transfer fails
            DataIntegrityError: If verification fails
            FileNotFoundError: If local path doesn't exist
        """
        try:
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"Local path not found: {local_path}")
            
            # Perform transfer with detailed error reporting
            if os.path.isdir(local_path):
                self.logger.debug(f"Starting directory upload: {local_path} -> {remote_path}")
                self.sftp_service.transfer_directory(local_path, remote_path, 'upload')
            else:
                self.logger.debug(f"Starting file upload: {local_path} -> {remote_path}")
                self.sftp_service.transfer_file(local_path, remote_path, 'upload')
            
            # Verify integrity
            self.logger.debug(f"Verifying upload integrity: {local_path} <-> {remote_path}")
            self.sftp_service.verify_integrity(local_path, remote_path)
            self.logger.info("Upload and verification completed successfully")
            
        except (NetworkError, DataIntegrityError, FileNotFoundError) as e:
            self.logger.error(f"Upload operation failed: {e}")
            raise  # Re-raise to be handled by retry mechanism
        except Exception as e:
            self.logger.error(f"Unexpected error during upload operation: {e}")
            # Convert unexpected errors to NetworkError for consistent handling
            raise NetworkError(f"Unexpected error during upload: {str(e)}")
    
    def _download_with_verification(self, remote_path: str, local_path: str) -> None:
        """
        Download file/directory and verify integrity with enhanced error handling.
        
        Args:
            remote_path: Remote source path
            local_path: Local destination path
            
        Raises:
            NetworkError: If transfer fails
            DataIntegrityError: If verification fails
        """
        try:
            # Perform transfer with enhanced error handling
            # Use the new is_remote_dir method to determine transfer type
            if self.sftp_service.is_remote_dir(remote_path):
                self.logger.debug(f"Starting directory download: {remote_path} -> {local_path}")
                self.sftp_service.transfer_directory(local_path, remote_path, 'download')
            else:
                self.logger.debug(f"Starting file download: {remote_path} -> {local_path}")
                self.sftp_service.transfer_file(local_path, remote_path, 'download')
            
            # Verify integrity
            self.logger.debug(f"Verifying download integrity: {local_path} <-> {remote_path}")
            self.sftp_service.verify_integrity(local_path, remote_path)
            self.logger.info("Download and verification completed successfully")
            
        except (NetworkError, DataIntegrityError) as e:
            self.logger.error(f"Download operation failed: {e}")
            raise  # Re-raise to be handled by retry mechanism
        except Exception as e:
            self.logger.error(f"Unexpected error during download operation: {e}")
            # Convert unexpected errors to NetworkError for consistent handling
            raise NetworkError(f"Unexpected error during download: {str(e)}")
    
    def _retry_operation(self, operation_func, operation_name: str) -> bool:
        """
        Retry operation with exponential backoff.
        
        Args:
            operation_func: Function to retry
            operation_name: Name of operation for logging
            
        Returns:
            True if operation succeeded, False if all retries failed
        """
        for attempt in range(self.max_retries + 1):
            try:
                operation_func()
                return True
                
            except DataIntegrityError as e:
                self.logger.error(f"Data integrity error in {operation_name} (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries:
                    return False
                
            except NetworkError as e:
                self.logger.warning(f"Network error in {operation_name} (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries:
                    return False
            except Exception as e:
                self.logger.error(f"Unexpected error in {operation_name} (attempt {attempt + 1}): {e}")
                if attempt == self.max_retries:
                    return False
            
            if attempt < self.max_retries:
                # Exponential backoff
                delay = self.retry_delay * (2 ** attempt)
                self.logger.info(f"Retrying {operation_name} in {delay} seconds...")
                time.sleep(delay)
        
        return False
    
    def _publish_success_message(self, command: str, payload: Dict[str, Any], correlation_id: str) -> None:
        """Publish success message to conductor queue."""
        try:
            self.message_broker.publish(
                queue_name=self.conductor_queue,
                command=command,
                payload=payload,
                correlation_id=correlation_id
            )
            self.logger.debug(f"Published success message: {command}", extra={'correlation_id': correlation_id})
        except Exception as e:
            self.logger.error(f"Failed to publish success message: {e}", extra={'correlation_id': correlation_id})
            # Don't re-raise as this is a non-critical operation
    
    def _publish_failure_message(self, command: str, payload: Dict[str, Any], correlation_id: str) -> None:
        """Publish failure message to conductor queue with DLQ support."""
        try:
            self.message_broker.publish(
                queue_name=self.conductor_queue,
                command=command,
                payload=payload,
                correlation_id=correlation_id
            )
            self.logger.debug(f"Published failure message: {command}", extra={'correlation_id': correlation_id})
        except Exception as e:
            self.logger.error(f"Failed to publish failure message: {e}", extra={'correlation_id': correlation_id})
            # Don't re-raise as this is a non-critical operation, but log it as critical
            # The DLQ mechanism in messaging.py will handle failed publish operations
    
    def run(self):
        """Start listening for messages."""
        self.logger.info("File Transfer worker starting...")
        
        try:
            queue_name = self.config.get('file_transfer', {}).get('queue_name', 'file_transfer_queue')
            self.message_broker.consume(
                queue_name=queue_name,
                callback=self.on_message_received
            )
        finally:
            self.sftp_service.close()
            self.logger.info("File Transfer worker stopped")