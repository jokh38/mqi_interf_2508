# File: src/common/ssh_client_manager.py
"""
Manages SSH connections using paramiko.
"""
import paramiko
from contextlib import contextmanager
from typing import Dict, Any, Generator
import os

from .logger import get_logger

class SSHClientManager:
    """Manages SSH connections."""

    def __init__(self, config: Dict[str, Any]):
        self.ssh_config = config.get('ssh', {})
        self.logger = get_logger(__name__)
        if not self.ssh_config:
            raise ValueError("SSH configuration is missing in the config file.")

    @contextmanager
    def get_client(self) -> Generator[paramiko.SSHClient, None, None]:
        """
        Provides a connected paramiko.SSHClient as a context manager.
        Handles connection and closure.
        """
        client = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            hostname = self.ssh_config.get('host')
            port = self.ssh_config.get('port', 22)
            username = self.ssh_config.get('username')
            key_path = self.ssh_config.get('private_key_path')

            if not all([hostname, username, key_path]):
                raise ValueError("SSH config is missing host, user, or key_path.")

            # Ensure key_path is absolute
            if not os.path.isabs(key_path):
                # Assuming key_path is relative to the project root
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
                key_path = os.path.join(project_root, key_path)

            if not os.path.exists(key_path):
                raise FileNotFoundError(f"SSH private key not found at: {key_path}")

            self.logger.info(f"Connecting to {username}@{hostname}:{port} using key {key_path}")
            
            client.connect(
                hostname=hostname,
                port=port,
                username=username,
                key_filename=key_path
            )
            yield client
        except paramiko.AuthenticationException as e:
            self.logger.error(f"SSH Authentication Failed: {e}. Check credentials and key permissions.")
            raise
        except Exception as e:
            self.logger.error(f"SSH connection or command execution failed: {e}")
            raise
        finally:
            if client:
                client.close()
                self.logger.debug("SSH connection closed.")
