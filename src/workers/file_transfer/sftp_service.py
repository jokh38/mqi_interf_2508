"""
SFTP service for file transfer operations.
"""

import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, Optional, Generator
from paramiko import SFTPClient

from src.common.exceptions import NetworkError, DataIntegrityError
from src.common.logger import get_logger
from src.common.ssh_base import SSHConnectionManager
from src.workers.file_transfer.utils import calculate_local_checksum, calculate_remote_checksum, calculate_directory_checksum


class SftpService(SSHConnectionManager):
    """Service for handling SFTP file transfers with integrity verification."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize SFTP service with configuration.
        
        Args:
            config: SFTP configuration containing host, port, username, private_key_path
        """
        super().__init__(config)
        self._sftp_client: Optional[SFTPClient] = None
        self.logger = get_logger(__name__)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with resource cleanup."""
        self.close()
        return False
    
    @contextmanager
    def sftp_connection(self) -> Generator[SFTPClient, None, None]:
        """Context manager for SFTP connections with automatic cleanup."""
        sftp_client = None
        try:
            sftp_client = self._get_sftp_client()
            yield sftp_client
        except Exception as e:
            self.logger.error(f"SFTP operation failed: {e}")
            raise
        finally:
            # Don't close the cached client, just ensure it's in good state
            if sftp_client and sftp_client != self._sftp_client:
                try:
                    sftp_client.close()
                except (OSError, Exception) as e:
                    self.logger.debug(f"Error closing temporary SFTP client: {e}")
    
    def _get_sftp_client(self) -> SFTPClient:
        """
        Create and return an SFTP connection object.
        
        Returns:
            Active SFTP client
            
        Raises:
            NetworkError: If connection fails
        """
        if self._sftp_client:
            try:
                # Test connection with minimal operation
                self._sftp_client.listdir('.')
                return self._sftp_client
            except Exception as e:
                # Connection lost, log and create new one
                self.logger.warning(f"SFTP connection test failed for {self.host}:{self.port}, reconnecting: {e}")
                self._close_sftp()
        
        try:
            # Use base class SSH connection
            ssh_client = self._connect()
            
            # Create SFTP client
            self._sftp_client = ssh_client.open_sftp()
            
            if self._sftp_client is None:
                raise NetworkError("Failed to create SFTP client")
            
            return self._sftp_client
            
        except Exception as e:
            raise NetworkError(f"Failed to establish SFTP connection: {e}")
    
    def _close_sftp(self):
        """Close SFTP connection if active."""
        if self._sftp_client:
            try:
                self._sftp_client.close()
            except (OSError, Exception) as e:
                self.logger.debug(f"Error closing SFTP client: {e}")
            finally:
                self._sftp_client = None
    
    @contextmanager
    def _sftp_connection_context(self) -> Generator[SFTPClient, None, None]:
        """
        Context manager for SFTP connections that ensures proper cleanup.
        
        Yields:
            Active SFTP client
            
        Raises:
            NetworkError: If connection fails
        """
        client = None
        try:
            client = self._get_sftp_client()
            yield client
        except Exception:
            # Close connection on error to prevent leaks
            if client:
                try:
                    client.close()
                except (OSError, Exception) as e:
                    self.logger.debug(f"Error closing SFTP client on error: {e}")
                self._sftp_client = None
            raise
        finally:
            # Don't close the connection here as it's reused
            # Only close on explicit close() or error
            pass
    
    def transfer_directory(self, local_path: str, remote_path: str, direction: str) -> None:
        """
        Transfer directory between local and remote locations.
        
        Args:
            local_path: Path to local directory
            remote_path: Path to remote directory
            direction: 'upload' for local->remote, 'download' for remote->local
            
        Raises:
            NetworkError: If transfer fails
            ValueError: If direction is invalid
        """
        if direction not in ['upload', 'download']:
            raise ValueError(f"Invalid direction: {direction}. Must be 'upload' or 'download'")
        
        try:
            with self._sftp_connection_context() as sftp_client:
                if direction == 'upload':
                    self._upload_directory(sftp_client, local_path, remote_path)
                else:
                    self._download_directory(sftp_client, remote_path, local_path)
        except NetworkError:
            raise
        except Exception as e:
            self.logger.error(f"Directory transfer failed - direction: {direction}, local: {local_path}, remote: {remote_path}, error: {e}")
            raise NetworkError(f"Directory transfer failed ({direction}): {e}")
    
    def transfer_file(self, local_path: str, remote_path: str, direction: str) -> None:
        """
        Transfer single file between local and remote locations.
        
        Args:
            local_path: Path to local file
            remote_path: Path to remote file
            direction: 'upload' for local->remote, 'download' for remote->local
            
        Raises:
            NetworkError: If transfer fails
            ValueError: If direction is invalid
        """
        if direction not in ['upload', 'download']:
            raise ValueError(f"Invalid direction: {direction}. Must be 'upload' or 'download'")
        
        try:
            with self._sftp_connection_context() as sftp_client:
                if direction == 'upload':
                    # Ensure remote directory exists
                    remote_dir = str(Path(remote_path).parent)
                    self._ensure_remote_directory(sftp_client, remote_dir)
                    self.logger.debug(f"Uploading file: {local_path} -> {remote_path}")
                    sftp_client.put(local_path, remote_path)
                    self.logger.debug(f"Successfully uploaded: {local_path} -> {remote_path}")
                else:
                    # Ensure local directory exists
                    local_dir = str(Path(local_path).parent)
                    os.makedirs(local_dir, exist_ok=True)
                    self.logger.debug(f"Downloading file: {remote_path} -> {local_path}")
                    sftp_client.get(remote_path, local_path)
                    self.logger.debug(f"Successfully downloaded: {remote_path} -> {local_path}")
        except NetworkError:
            raise
        except Exception as e:
            self.logger.error(f"File transfer failed - direction: {direction}, local: {local_path}, remote: {remote_path}, error: {e}")
            raise NetworkError(f"File transfer failed ({direction}): {e}")
    
    def verify_integrity(self, local_path: str, remote_path: str) -> bool:
        """
        Verify integrity of transferred files by comparing checksums.
        
        Args:
            local_path: Path to local file/directory
            remote_path: Path to remote file/directory
            
        Returns:
            True if checksums match
            
        Raises:
            DataIntegrityError: If checksums don't match
            NetworkError: If verification fails due to network issues
        """
        try:
            with self._sftp_connection_context() as sftp_client:
                if os.path.isdir(local_path):
                    local_checksum = calculate_directory_checksum(local_path)
                    remote_checksum = calculate_directory_checksum(remote_path, sftp_client)
                else:
                    local_checksum = calculate_local_checksum(local_path)
                    remote_checksum = calculate_remote_checksum(sftp_client, remote_path)
                
                if local_checksum != remote_checksum:
                    raise DataIntegrityError(
                        f"Checksum mismatch - Local: {local_checksum}, Remote: {remote_checksum}"
                    )
                
                return True
                
        except DataIntegrityError:
            raise
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(f"Integrity verification failed: {e}")
    
    def _upload_directory(self, sftp_client: SFTPClient, local_path: str, remote_path: str) -> None:
        """Upload directory recursively."""
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local directory not found: {local_path}")
        
        # Ensure remote directory exists
        self._ensure_remote_directory(sftp_client, remote_path)
        
        for root, dirs, files in os.walk(local_path):
            # Create remote directories
            relative_root = os.path.relpath(root, local_path)
            if relative_root != '.':
                remote_root = f"{remote_path.rstrip('/')}/{relative_root}".replace('\\', '/')
                self._ensure_remote_directory(sftp_client, remote_root)
            else:
                remote_root = remote_path
            
            # Upload files
            for file_name in files:
                local_file = os.path.join(root, file_name)
                remote_file = f"{remote_root.rstrip('/')}/{file_name}".replace('\\', '/')
                sftp_client.put(local_file, remote_file)
    
    def _download_directory(self, sftp_client: SFTPClient, remote_path: str, local_path: str) -> None:
        """Download directory recursively."""
        # Ensure local directory exists
        os.makedirs(local_path, exist_ok=True)
        
        def _download_recursive(remote_dir: str, local_dir: str):
            try:
                items = sftp_client.listdir_attr(remote_dir)
                for item in items:
                    remote_item_path = f"{remote_dir.rstrip('/')}/{item.filename}"
                    local_item_path = os.path.join(local_dir, item.filename)
                    
                    if item.st_mode is not None and stat.S_ISDIR(item.st_mode):
                        # Directory - create locally and recurse
                        os.makedirs(local_item_path, exist_ok=True)
                        _download_recursive(remote_item_path, local_item_path)
                    else:
                        # File - download
                        sftp_client.get(remote_item_path, local_item_path)
            except Exception as e:
                self.logger.error(f"Failed to download directory - remote: {remote_dir}, local: {local_dir}, error: {e}")
                raise NetworkError(f"Failed to download directory {remote_dir}: {e}")
        
        _download_recursive(remote_path, local_path)
    
    def _ensure_remote_directory(self, sftp_client: SFTPClient, remote_path: str) -> None:
        """Ensure remote directory exists, creating if necessary."""
        if remote_path in ['', '/']:
            return
        
        # Check if directory already exists
        directory_exists = self._check_remote_directory_exists(sftp_client, remote_path)
        if directory_exists:
            return
        
        # Directory doesn't exist, create parent directories first
        parent_dir = str(Path(remote_path).parent)
        if parent_dir != remote_path:
            self._ensure_remote_directory(sftp_client, parent_dir)
        
        # Create the directory
        try:
            sftp_client.mkdir(remote_path)
        except Exception as e:
            # Check again in case of race condition
            if not self._check_remote_directory_exists(sftp_client, remote_path):
                raise NetworkError(f"Failed to create remote directory {remote_path}: {e}")
    
    def _check_remote_directory_exists(self, sftp_client: SFTPClient, remote_path: str) -> bool:
        """Check if remote directory exists without using exceptions for control flow."""
        try:
            stat_info = sftp_client.stat(remote_path)
            return stat.S_ISDIR(stat_info.st_mode)
        except Exception:
            return False
    
    def _close_connections(self):
        """Close SFTP and SSH connections."""
        if self._sftp_client:
            try:
                self._sftp_client.close()
            except Exception as e:
                self.logger.warning(f"Error closing SFTP client: {e}")
            finally:
                self._sftp_client = None
        
        if hasattr(self, '_ssh_client') and self._ssh_client:
            try:
                self._ssh_client.close()
            except Exception as e:
                self.logger.warning(f"Error closing SSH client: {e}")
            finally:
                self._ssh_client = None
    
    def is_remote_dir(self, remote_path: str) -> bool:
        """
        Check if a remote path is a directory without raising exceptions.
        
        Args:
            remote_path: Remote path to check
            
        Returns:
            True if remote_path is a directory, False otherwise
        """
        try:
            with self.sftp_connection() as sftp_client:
                file_stat = sftp_client.stat(remote_path)
                return stat.S_ISDIR(file_stat.st_mode)
        except Exception as e:
            self.logger.debug(f"Failed to check if {remote_path} is directory: {e}")
            return False
    
    def close(self):
        """Close all connections."""
        self._close_connections()