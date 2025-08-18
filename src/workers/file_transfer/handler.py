"""
File Transfer message handler.
"""

import os
import time
import threading
from typing import Dict, Any
from datetime import datetime

from src.common.messaging import MessageBroker
from src.common.logger import get_logger
from src.common.logging_setup import correlation_id_var
from src.common.db_utils import DatabaseManager
from src.common.exceptions import NetworkError, DataIntegrityError, ConfigurationError
from src.workers.file_transfer.sftp_service import SftpService


class FileTransferHandler:
    """Handler for file transfer messages."""

    def __init__(self, config: Dict[str, Any], message_broker: MessageBroker, db_manager: DatabaseManager):
        """Initialize file transfer handler."""
        self.config = config
        self.message_broker = message_broker
        self.db_manager = db_manager
        self.logger = get_logger(__name__)
        self._operation_lock = threading.Lock()

        sftp_config = config.get('sftp', {})
        if not sftp_config:
            raise ConfigurationError("SFTP configuration not found")
        self.sftp_service = SftpService(sftp_config)

        self.max_retries = config.get('file_transfer', {}).get('max_retries', 3)
        self.retry_delay = config.get('file_transfer', {}).get('retry_delay_sec', 5)
        self.conductor_queue = config.get('queues', {}).get('conductor', 'conductor_queue')

    def on_message_received(self, message_data: Dict[str, Any], correlation_id: str) -> None:
        """Handle received messages with correlation ID context."""
        correlation_id_var.set(correlation_id)
        
        if not self._validate_message(message_data):
            return

        try:
            command = message_data.get('command')
            payload = message_data.get('payload', {})
            self.logger.info(f"Received command: {command}")

            if command == 'upload_case':
                self._handle_upload_case(payload)
            elif command == 'download_results':
                self._handle_download_results(payload)

        except (NetworkError, DataIntegrityError, ConfigurationError) as e:
            self.logger.error(f"File transfer error handling message: {e}")
            self._publish_failure_message(
                "file_transfer_failed",
                {
                    "error": str(e),
                    "command": message_data.get('command'),
                    "error_type": type(e).__name__,
                    "timestamp": datetime.utcnow().isoformat(),
                    "correlation_id": correlation_id
                }
            )
        except Exception as e:
            self.logger.error(f"Unexpected error handling message: {e}", exc_info=True)
            self._publish_failure_message(
                "file_transfer_failed",
                {
                    "error": f"Unexpected error: {str(e)}",
                    "command": message_data.get('command'),
                    "error_type": "UnexpectedError",
                    "timestamp": datetime.utcnow().isoformat(),
                    "correlation_id": correlation_id
                }
            )

    def _validate_message(self, message_data: Dict[str, Any]) -> bool:
        """Validate incoming message format and content."""
        try:
            if not isinstance(message_data, dict):
                raise ValueError("Message must be a dictionary")
            command = message_data.get('command')
            if command not in ['upload_case', 'download_results']:
                raise ValueError(f"Unsupported command type: {command}")
            if not isinstance(message_data.get('payload'), dict):
                raise ValueError("Missing or invalid 'payload' field")
            return True
        except (ValueError, TypeError, KeyError) as e:
            self.logger.error(f"Message validation failed: {e}")
            self._publish_failure_message(
                "malformed_message",
                {
                    'error': str(e),
                    'timestamp': datetime.utcnow().isoformat(),
                    'original_message': str(message_data)[:500]
                }
            )
            return False

    def _handle_upload_case(self, payload: Dict[str, Any]) -> None:
        """Handle case upload request."""
        try:
            local_path = payload['local_path']
            remote_path = payload['remote_path']
            case_id = payload['case_id']
        except KeyError as e:
            self.logger.error(f"Invalid payload for upload case, missing key: {e}")
            self._publish_failure_message("file_transfer_failed", {"error": f"Missing key: {e}", "operation": "upload"})
            return

        self.logger.info(f"Starting case upload: {case_id} from {local_path} to {remote_path}")
        with self._operation_lock:
            success = self._retry_operation(
                lambda: self._upload_with_verification(local_path, remote_path),
                f"upload case {case_id}"
            )
        
        if success:
            self.logger.info(f"Case upload completed successfully: {case_id}")
            self._publish_success_message("case_upload_completed", {"case_id": case_id, "local_path": local_path, "remote_path": remote_path})
        else:
            self.logger.error(f"Case upload failed after all retries: {case_id}")
            self._publish_failure_message("file_transfer_failed", {"case_id": case_id, "operation": "upload"})

    def _handle_download_results(self, payload: Dict[str, Any]) -> None:
        """Handle results download request."""
        try:
            local_path = payload['local_path']
            remote_path = payload['remote_path']
            case_id = payload['case_id']
        except KeyError as e:
            self.logger.error(f"Invalid payload for download results, missing key: {e}")
            self._publish_failure_message("file_transfer_failed", {"error": f"Missing key: {e}", "operation": "download"})
            return

        self.logger.info(f"Starting results download: {case_id} from {remote_path} to {local_path}")
        with self._operation_lock:
            success = self._retry_operation(
                lambda: self._download_with_verification(remote_path, local_path),
                f"download results {case_id}"
            )

        if success:
            self.logger.info(f"Results download completed successfully: {case_id}")
            self._publish_success_message("results_download_completed", {"case_id": case_id, "local_path": local_path, "remote_path": remote_path})
        else:
            self.logger.error(f"Results download failed after all retries: {case_id}")
            self._publish_failure_message("file_transfer_failed", {"case_id": case_id, "operation": "download"})

    def _upload_with_verification(self, local_path: str, remote_path: str):
        """Upload file/directory and verify integrity."""
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local path not found: {local_path}")
        
        transfer_type = 'directory' if os.path.isdir(local_path) else 'file'
        self.logger.debug(f"Starting {transfer_type} upload: {local_path} -> {remote_path}")
        
        if transfer_type == 'directory':
            self.sftp_service.transfer_directory(local_path, remote_path, 'upload')
        else:
            self.sftp_service.transfer_file(local_path, remote_path, 'upload')
        
        self.logger.debug(f"Verifying upload integrity...")
        self.sftp_service.verify_integrity(local_path, remote_path)
        self.logger.info("Upload and verification completed successfully")

    def _download_with_verification(self, remote_path: str, local_path: str):
        """Download file/directory and verify integrity."""
        transfer_type = 'directory' if self.sftp_service.is_remote_dir(remote_path) else 'file'
        self.logger.debug(f"Starting {transfer_type} download: {remote_path} -> {local_path}")
        
        if transfer_type == 'directory':
            self.sftp_service.transfer_directory(local_path, remote_path, 'download')
        else:
            self.sftp_service.transfer_file(local_path, remote_path, 'download')
            
        self.logger.debug(f"Verifying download integrity...")
        self.sftp_service.verify_integrity(local_path, remote_path)
        self.logger.info("Download and verification completed successfully")

    def _retry_operation(self, operation_func, operation_name: str) -> bool:
        """Retry operation with exponential backoff."""
        for attempt in range(self.max_retries + 1):
            try:
                operation_func()
                return True
            except (DataIntegrityError, NetworkError, FileNotFoundError) as e:
                self.logger.warning(f"Error in {operation_name} (attempt {attempt + 1}/{self.max_retries+1}): {e}")
                if attempt == self.max_retries:
                    return False
                delay = self.retry_delay * (2 ** attempt)
                self.logger.info(f"Retrying {operation_name} in {delay} seconds...")
                time.sleep(delay)
            except Exception as e:
                self.logger.error(f"Unexpected error in {operation_name} on attempt {attempt + 1}", exc_info=True)
                if attempt == self.max_retries:
                    return False
                delay = self.retry_delay * (2 ** attempt)
                time.sleep(delay)
        return False

    def _publish_success_message(self, command: str, payload: Dict[str, Any]) -> None:
        """Publish success message to conductor queue."""
        try:
            self.message_broker.publish(
                queue_name=self.conductor_queue,
                command=command,
                payload=payload,
                correlation_id=correlation_id_var.get()
            )
            self.logger.debug(f"Published success message: {command}")
        except Exception as e:
            self.logger.error(f"Failed to publish success message: {e}", exc_info=True)

    def _publish_failure_message(self, command: str, payload: Dict[str, Any]) -> None:
        """Publish failure message to conductor queue."""
        try:
            self.message_broker.publish(
                queue_name=self.conductor_queue,
                command=command,
                payload=payload,
                correlation_id=correlation_id_var.get()
            )
            self.logger.debug(f"Published failure message: {command}")
        except Exception as e:
            self.logger.error(f"Failed to publish failure message: {e}", exc_info=True)

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