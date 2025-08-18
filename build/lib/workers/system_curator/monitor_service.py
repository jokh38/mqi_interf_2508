"""
Monitor service for System Curator worker.
Handles SSH connections and GPU metrics collection from remote systems.
"""

from typing import List, Dict, Any
from src.common.exceptions import RemoteExecutionError, ConfigurationError, format_error_message
from src.common.logger import get_logger
from src.common.ssh_base import SSHManager


def fetch_gpu_metrics(config: Dict[str, Any], db_manager=None) -> List[Dict[str, Any]]:
    """
    Fetch GPU metrics from remote system via SSH using centralized configuration.

    Args:
        config: Full configuration dictionary containing 'ssh' and 'curator' sections
        db_manager: Database manager instance for logging (optional)

    Returns:
        List of dictionaries containing GPU metrics

    Raises:
        ConfigurationError: If required configuration is missing
        RemoteExecutionError: If SSH connection or command execution fails
    """
    logger = get_logger(__name__, db_manager)

    ssh_config = config.get('ssh', {})
    gpu_command = config.get('curator', {}).get('gpu_monitor_command')

    if not ssh_config:
        raise ConfigurationError("Missing 'ssh' configuration section")
    if not gpu_command:
        raise ConfigurationError("Missing 'curator.gpu_monitor_command' configuration")

    ssh_manager = SSHManager(ssh_config, db_manager)

    try:
        with ssh_manager.get_transient_connection() as client:
            stdin, stdout, stderr = client.exec_command(gpu_command)
            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                stderr_output = stderr.read().decode('utf-8').strip()
                message = format_error_message(
                    operation="GPU command execution",
                    error_details=stderr_output,
                    context={"exit_code": exit_status, "command": gpu_command}
                )
                raise RemoteExecutionError(message)

            stdout_output = stdout.read().decode('utf-8').strip()

            if not stdout_output:
                logger.info("No GPU data found in command output")
                return []

            gpu_metrics = []
            for line in stdout_output.split('\n'):
                if line.strip():
                    try:
                        parts = [part.strip() for part in line.split(',')]
                        if len(parts) != 6:
                            raise ValueError(f"Expected 6 fields, got {len(parts)}")

                        gpu_data = {
                            'gpu_id': int(parts[0]),
                            'uuid': parts[1],
                            'utilization': int(parts[2]),
                            'memory_used_mb': int(parts[3]),
                            'memory_total_mb': int(parts[4]),
                            'temperature_c': int(parts[5])
                        }
                        gpu_metrics.append(gpu_data)

                    except (ValueError, IndexError) as e:
                        raise RemoteExecutionError(f"Failed to parse nvidia-smi output: {e}")

            logger.info(f"Successfully fetched metrics for {len(gpu_metrics)} GPUs")
            return gpu_metrics

    except Exception as e:
        if isinstance(e, (RemoteExecutionError, ConfigurationError)):
            raise
        message = format_error_message(
            operation="GPU metrics collection",
            error_details=str(e),
            context={"host": ssh_config.get('host')},
            suggestion="Check system health and GPU driver status"
        )
        raise RemoteExecutionError(message)