"""
Base SSH connection manager for reuse across workers.
"""

import paramiko
from typing import Dict, Any, Generator, Optional
from contextlib import contextmanager

from .exceptions import NetworkError, format_connection_error
from .logger import get_logger


class SSHConnectionManager:
    """Base SSH connection manager with common functionality."""
    
    def __init__(self, config: Dict[str, Any], db_manager=None):
        """
        Initialize SSH connection manager.
        
        Args:
            config: SSH configuration containing host, port, username, private_key_path
            db_manager: Database manager instance for logging (optional)
        """
        self.host = config.get('host')
        self.port = config.get('port', 22)
        self.username = config.get('username')  # Standardized field name
        self.private_key_path = config.get('private_key_path')
        self.timeout = config.get('timeout', 30)
        
        # Initialize logger with database manager
        self.logger = get_logger(__name__, db_manager)
        
        if not all([self.host, self.username]):
            raise NetworkError("Missing required SSH configuration: host, username")
        
        self._ssh_client: Optional[paramiko.SSHClient] = None
    
    def _create_ssh_client(self) -> paramiko.SSHClient:
        """
        Create and configure SSH client.
        
        Returns:
            Configured SSH client
        """
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return ssh_client
    
    def _connect(self) -> paramiko.SSHClient:
        """
        Establish SSH connection.
        
        Returns:
            Connected SSH client
            
        Raises:
            NetworkError: If connection fails
        """
        if self._ssh_client:
            try:
                # Test existing connection
                transport = self._ssh_client.get_transport()
                if transport and transport.is_active():
                    return self._ssh_client
            except Exception:
                # Connection lost, create new one
                self._close_connection()
        
        try:
            self._ssh_client = self._create_ssh_client()
            
            connect_kwargs = {
                'hostname': self.host,
                'port': self.port,
                'username': self.username,
                'timeout': self.timeout
            }
            
            if self.private_key_path:
                connect_kwargs['key_filename'] = self.private_key_path
            
            self.logger.info(f"Connecting to {self.username}@{self.host}:{self.port}")
            self._ssh_client.connect(**connect_kwargs)
            self.logger.info("SSH connection established")
            
            if self._ssh_client is None:
                raise NetworkError("Failed to establish SSH connection")
            
            return self._ssh_client
            
        except Exception as e:
            message = format_connection_error("SSH", str(e), self.host)
            raise NetworkError(message)
    
    def _close_connection(self):
        """Close SSH connection if active."""
        if self._ssh_client is not None:
            try:
                self._ssh_client.close()
            except Exception as e:
                self.logger.warning(f"Error closing SSH connection: {e}")
            finally:
                self._ssh_client = None
    
    @contextmanager
    def get_connection(self) -> Generator[paramiko.SSHClient, None, None]:
        """
        Context manager for SSH connection.
        
        ⚠️ WARNING - NON-STANDARD BEHAVIOR ⚠️
        This context manager intentionally does NOT close the connection when 
        exiting the context. The connection is kept alive for reuse across 
        multiple operations to improve performance.
        
        USAGE GUIDE:
        - Use this when you need multiple SSH operations in sequence
        - The connection will be automatically reused for subsequent calls
        - Call close() explicitly when done with all SSH operations
        - Connection is automatically tested and recreated if stale
        
        Example:
            ssh_manager = SSHConnectionManager(config)
            
            # Multiple operations using the same connection
            with ssh_manager.get_connection() as ssh:
                stdin, stdout, stderr = ssh.exec_command("command1")
            
            with ssh_manager.get_connection() as ssh:  # Reuses same connection
                stdin, stdout, stderr = ssh.exec_command("command2")
            
            # Clean up when completely done
            ssh_manager.close()
        
        Yields:
            SSH client connection
        """
        client = None
        try:
            client = self._connect()
            yield client
        except Exception:
            # If an error occurs, close the potentially corrupted connection
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass  # Ignore errors during cleanup
            self._ssh_client = None
            raise
        finally:
            # Keep connection alive for reuse, don't close here unless error occurred
            pass
    
    def close(self):
        """Close connection and cleanup resources."""
        self._close_connection()