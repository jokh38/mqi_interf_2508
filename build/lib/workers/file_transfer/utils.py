"""
Utility functions for file transfer operations.
"""

import hashlib
import os
from typing import Optional, List
from paramiko import SFTPClient


def calculate_local_checksum(file_path: str) -> str:
    """
    Calculate SHA256 checksum of a local file.

    Args:
        file_path: Path to the local file

    Returns:
        SHA256 checksum as hexadecimal string

    Raises:
        FileNotFoundError: If the file doesn't exist
        IOError: If file cannot be read
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    sha256_hash = hashlib.sha256()

    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
    except IOError as e:
        raise IOError(f"Cannot read file {file_path}: {e}")

    return sha256_hash.hexdigest()


def calculate_remote_checksum(sftp_client: SFTPClient, remote_file_path: str) -> str:
    """
    Calculate SHA256 checksum of a remote file via SFTP.

    Args:
        sftp_client: SFTP client connection
        remote_file_path: Path to the remote file

    Returns:
        SHA256 checksum as hexadecimal string

    Raises:
        FileNotFoundError: If the remote file doesn't exist
        IOError: If file cannot be read
    """
    sha256_hash = hashlib.sha256()

    try:
        with sftp_client.open(remote_file_path, 'rb') as remote_file:
            for chunk in iter(lambda: remote_file.read(8192), b""):
                sha256_hash.update(chunk)
    except FileNotFoundError:
        raise FileNotFoundError(f"Remote file not found: {remote_file_path}")
    except IOError as e:
        raise IOError(f"Cannot read remote file {remote_file_path}: {e}")

    return sha256_hash.hexdigest()


def calculate_directory_checksum(directory_path: str, sftp_client: Optional[SFTPClient] = None) -> str:
    """
    Calculate combined SHA256 checksum for all files in a directory.

    Args:
        directory_path: Path to the directory
        sftp_client: SFTP client for remote directories, None for local

    Returns:
        Combined SHA256 checksum as hexadecimal string

    Raises:
        FileNotFoundError: If the directory doesn't exist
        IOError: If files cannot be read
    """
    combined_hash = hashlib.sha256()

    if sftp_client is None:
        # Local directory
        if not os.path.exists(directory_path):
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        for root, dirs, files in os.walk(directory_path):
            for file_name in sorted(files):  # Sort for consistent ordering
                file_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(file_path, directory_path)

                # Include relative path in hash for structure verification
                combined_hash.update(relative_path.encode('utf-8'))

                # Add file content hash
                file_checksum = calculate_local_checksum(file_path)
                combined_hash.update(file_checksum.encode('utf-8'))
    else:
        # Remote directory
        try:
            file_list = _get_remote_file_list(sftp_client, directory_path)
            for relative_path in sorted(file_list):
                remote_file_path = f"{directory_path.rstrip('/')}/{relative_path}"

                # Include relative path in hash for structure verification
                combined_hash.update(relative_path.encode('utf-8'))

                # Add file content hash
                file_checksum = calculate_remote_checksum(sftp_client, remote_file_path)
                combined_hash.update(file_checksum.encode('utf-8'))
        except Exception as e:
            raise IOError(f"Cannot access remote directory {directory_path}: {e}")

    return combined_hash.hexdigest()


def _get_remote_file_list(sftp_client: SFTPClient, directory_path: str) -> List[str]:
    """
    Get list of all files in remote directory recursively.

    Args:
        sftp_client: SFTP client connection
        directory_path: Remote directory path

    Returns:
        List of relative file paths
    """
    file_list = []

    def _walk_remote_dir(remote_path: str, relative_base: str = ""):
        try:
            items = sftp_client.listdir_attr(remote_path)
            for item in items:
                item_path = f"{remote_path.rstrip('/')}/{item.filename}"
                relative_path = f"{relative_base}/{item.filename}".lstrip('/')

                if item.st_mode and (item.st_mode & 0o040000):  # Directory
                    _walk_remote_dir(item_path, relative_path)
                else:  # Regular file
                    file_list.append(relative_path)
        except Exception:
            # Skip directories that can't be accessed
            pass

    _walk_remote_dir(directory_path)
    return file_list