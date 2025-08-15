"""
Unified SSH connection manager for reuse across workers.
This module provides a comprehensive SSH manager that supports both
persistent and transient (short-lived) connections.
"""

import os
import paramiko
from typing import Dict, Any, Generator, Optional
from contextlib import contextmanager

from .exceptions import NetworkError, ConfigurationError, format_connection_error
from .logger import get_logger


class SSHManager:
    """
    Unified SSH connection manager with support for persistent and transient connections.
    """

    def __init__(self, config: Dict[str, Any], db_manager=None):
        """
        Initialize SSH manager.
        The configuration can be a flat dictionary or nested under an 'ssh' key.
        Args:
            config: SSH configuration.
            db_manager: Database manager instance for logging (optional).
        """
        ssh_config = config.get('ssh', config)

        self.host = ssh_config.get('host')
        self.port = ssh_config.get('port', 22)
        self.username = ssh_config.get('username')
        self.private_key_path = ssh_config.get('private_key_path')
        self.timeout = ssh_config.get('timeout', 30)

        self.logger = get_logger(__name__, db_manager)

        if not all([self.host, self.username, self.private_key_path]):
            raise ConfigurationError("Missing required SSH config: host, username, or private_key_path.")

        self._resolve_key_path()

        self._persistent_client: Optional[paramiko.SSHClient] = None

    def _resolve_key_path(self):
        """Resolves the private key path to an absolute path."""
        if not os.path.isabs(self.private_key_path):
            # Assumes the path is relative to the project root if not absolute.
            # The project root is assumed to be two levels up from this file's directory.
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            self.private_key_path = os.path.join(project_root, self.private_key_path)

        if not os.path.exists(self.private_key_path):
            raise ConfigurationError(f"SSH private key not found at: {self.private_key_path}")

    def _create_ssh_client(self) -> paramiko.SSHClient:
        """Creates and configures a new SSH client instance."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def _connect(self, client: paramiko.SSHClient) -> None:
        """Establishes a connection using the provided client."""
        try:
            connect_kwargs = {
                'hostname': self.host,
                'port': self.port,
                'username': self.username,
                'key_filename': self.private_key_path,
                'timeout': self.timeout
            }
            self.logger.info(f"Connecting to {self.username}@{self.host}:{self.port}")
            client.connect(**connect_kwargs)
            self.logger.info("SSH connection established")
        except paramiko.AuthenticationException as e:
            self.logger.error(f"SSH Authentication Failed for {self.username}@{self.host}. Check credentials. Error: {e}")
            raise NetworkError(f"SSH Authentication Failed: {e}")
        except Exception as e:
            message = format_connection_error("SSH", str(e), self.host)
            self.logger.error(message)
            raise NetworkError(message)

    @contextmanager
    def get_transient_connection(self) -> Generator[paramiko.SSHClient, None, None]:
        """
        Provides a transient SSH connection that is automatically closed on exit.
        Ideal for single, isolated operations.
        Yields:
            A connected paramiko.SSHClient instance.
        """
        client = None
        try:
            client = self._create_ssh_client()
            self._connect(client)
            yield client
        finally:
            if client:
                client.close()
                self.logger.debug("Transient SSH connection closed.")

    @contextmanager
    def get_persistent_connection(self) -> Generator[paramiko.SSHClient, None, None]:
        """
        Provides a persistent SSH connection that is reused across multiple calls.
        The connection is NOT closed on exiting the context. Call close() explicitly.
        Yields:
            A connected paramiko.SSHClient instance.
        """
        try:
            if not self._persistent_client or not self._persistent_client.get_transport() or not self._persistent_client.get_transport().is_active():
                self.logger.info("No active persistent SSH client found. Creating a new one.")
                self._persistent_client = self._create_ssh_client()
                self._connect(self._persistent_client)

            yield self._persistent_client
        except Exception as e:
            self.logger.error(f"Failed to provide persistent SSH connection: {e}")
            # Ensure a failed client is cleaned up
            self.close()
            raise

    def close(self):
        """Closes the persistent SSH connection if it is active."""
        if self._persistent_client:
            try:
                self._persistent_client.close()
                self.logger.info("Persistent SSH connection closed.")
            except Exception as e:
                self.logger.warning(f"Error closing persistent SSH connection: {e}")
            finally:
                self._persistent_client = None