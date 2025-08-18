# File: src/common/remote_executor.py
"""
A simple remote command executor using SSH.
"""
from typing import Dict, Any, Tuple

from .ssh_client_manager import SSHClientManager
from .exceptions import RemoteExecutionError
from .logger import get_logger

class RemoteExecutor:
    """A simple class to execute commands on a remote server via SSH."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = get_logger(__name__)
        self.ssh_manager = SSHClientManager(config)

    def execute(self, command: str, timeout: int = 60) -> Tuple[str, str]:
        """
        Executes a command on the remote server.

        Args:
            command: The command to execute.
            timeout: The timeout for the command execution.

        Returns:
            A tuple containing the stdout and stderr from the command.

        Raises:
            RemoteExecutionError: If the command execution fails.
        """
        try:
            with self.ssh_manager.get_client() as ssh:
                stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
                stdout_str = stdout.read().decode('utf-8').strip()
                stderr_str = stderr.read().decode('utf-8').strip()

                if stderr_str and not stdout_str:
                    self.logger.error(f"Remote command failed: {stderr_str}")
                    raise RemoteExecutionError(f"Command execution failed: {stderr_str}")

                return stdout_str, stderr_str
        except Exception as e:
            self.logger.error(f"Failed to execute remote command: {e}")
            raise RemoteExecutionError(f"Failed to execute remote command: {e}") from e
