"""
SSH service module for remote command execution.

This module provides functionality to execute commands on remote hosts
via SSH connection and collect execution results.
"""

import paramiko
from typing import Dict, Any
from src.common.exceptions import RemoteExecutionError
from src.common.logger import get_logger
from src.common.ssh_base import SSHConnectionManager


def execute(command: str, ssh_config: Dict[str, Any], db_manager=None) -> Dict[str, Any]:
    """
    Execute a command on remote host via SSH.
    
    Args:
        command: Command string to execute
        ssh_config: SSH connection configuration containing:
            - host: Remote host address
            - port: SSH port (default 22)
            - username: SSH username  
            - private_key_path: Path to private key file
        db_manager: Database manager instance for logging (optional)
            
    Returns:
        Dictionary containing:
            - exit_code: Command exit code
            - stdout: Standard output as string
            - stderr: Standard error as string
            
    Raises:
        RemoteExecutionError: If SSH connection fails or command execution fails
    """
    # Initialize logger with database manager
    logger = get_logger(__name__, db_manager)
    
    ssh_manager = SSHConnectionManager(ssh_config, db_manager)
    
    try:
        with ssh_manager.get_connection() as ssh_client:
            # Execute command
            logger.info(f"Executing command: {command}")
            stdin, stdout, stderr = ssh_client.exec_command(command)
            
            # Collect results
            stdout_data = stdout.read().decode('utf-8').strip()
            stderr_data = stderr.read().decode('utf-8').strip()
            exit_code = stdout.channel.recv_exit_status()
            
            logger.info(f"Command completed with exit code: {exit_code}")
            
            result = {
                'exit_code': exit_code,
                'stdout': stdout_data,
                'stderr': stderr_data
            }
            
            # Check if command failed
            if exit_code != 0:
                error_msg = f"Command failed with exit code {exit_code}: {stderr_data}"
                logger.error(error_msg)
                raise RemoteExecutionError(error_msg)
            
            return result
        
    except paramiko.AuthenticationException as e:
        error_msg = f"SSH authentication failed: {e}"
        logger.error(error_msg)
        raise RemoteExecutionError(f"SSH authentication failed: {error_msg}")
    except paramiko.SSHException as e:
        error_msg = f"SSH error: {e}"
        logger.error(error_msg)
        raise RemoteExecutionError(f"SSH connection failed: {error_msg}")
    except Exception as e:
        error_msg = f"Unexpected error during SSH execution: {e}"
        logger.error(error_msg)
        raise RemoteExecutionError(f"Remote execution failed: {error_msg}")
    finally:
        ssh_manager.close()