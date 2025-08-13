"""
Process manager for MQI Communicator worker processes.
Handles lifecycle management of all system worker processes, including remote HPC processes.
"""

import subprocess
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional
import os
import sys
import paramiko

from .common.exceptions import ConfigurationError


class ProcessInfo:
    """Information about a managed worker process."""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize process information.
        
        Args:
            name: Process name
            config: Process configuration
        """
        self.name = name
        self.config = config
        self.remote_pid: Optional[int] = None
        self.restart_count = 0
        self.last_restart: Optional[float] = None
        self.is_failed_permanently = False
        self.consecutive_failures = 0
        
    def is_running(self, ssh_client: Optional[paramiko.SSHClient] = None) -> bool:
        """
        Check if the process is currently running, either locally or remotely.
        
        Args:
            ssh_client: Optional SSH client for remote process checking
            
        Returns:
            True if process is running, False otherwise
        """
        if self.remote_pid is None:
            return False
            
        if ssh_client and self.config.get('remote', False):
            try:
                # Use kill -0 to check if process exists without sending a signal
                stdin, stdout, stderr = ssh_client.exec_command(f"kill -0 {self.remote_pid}")
                exit_code = stdout.channel.recv_exit_status()
                return exit_code == 0
            except Exception:
                return False
        else:
            try:
                # Local process check
                import psutil
                return psutil.pid_exists(self.remote_pid)
            except Exception:
                return False
    
    def get_backoff_delay(self) -> float:
        """
        Calculate exponential backoff delay in seconds.
        
        Returns:
            Delay in seconds before next restart attempt
        """
        base_delay = self.config.get('restart_delay_sec', 30)
        max_delay = self.config.get('max_restart_delay_sec', 900)  # 15 minutes max
        
        # Exponential backoff: base_delay * (2 ^ consecutive_failures)
        delay = base_delay * (2 ** min(self.consecutive_failures, 6))  # Cap at 2^6 = 64x multiplier
        return min(delay, max_delay)
    
    def should_restart(self) -> bool:
        """
        Check if process should be restarted based on restart policy.
        
        Returns:
            True if process should be restarted, False if permanently failed
        """
        if self.is_failed_permanently:
            return False
            
        max_restarts = self.config.get('max_restart_attempts', 10)
        return self.restart_count < max_restarts


class ProcessManager:
    """
    Manager for all worker processes in the MQI Communicator system.
    
    Responsibilities:
    - Start and stop individual worker processes
    - Monitor process health and restart failed processes
    - Manage process dependencies and coordination
    - Log process status changes
    """
    
    # Map of process names to their module paths
    PROCESS_MODULES = {
        'conductor': 'src.conductor.main',
        'case_scanner': 'src.workers.case_scanner.main',
        'file_transfer': 'src.workers.file_transfer.main',
        'remote_executor': 'src.workers.remote_executor.main',
        'system_curator': 'src.workers.system_curator.main',
        'archiver': 'src.workers.archiver.main',
        'dashboard': 'src.dashboard.main'
    }
    
    def __init__(self, config: Dict[str, Any], db_manager, logger):
        """
        Initialize process manager.
        
        Args:
            config: System configuration
            db_manager: Database manager instance
            logger: Logger instance
        """
        if 'processes' not in config:
            raise ConfigurationError("Missing 'processes' configuration section")
            
        self.config = config
        self.db_manager = db_manager
        self.logger = logger
        self.hpc_config = self.config.get('hpc_config', {})
        
        # SSH client for remote management
        self.ssh_client: Optional[paramiko.SSHClient] = None
        if self.hpc_config.get('enabled', False):
            self._connect_ssh()

        # Thread synchronization for concurrent operations
        self._lock = threading.RLock()
        
        # Create process info for enabled processes only
        self.processes: Dict[str, ProcessInfo] = {}
        self._initialize_processes()
        
    def _connect_ssh(self):
        """Establish SSH connection to the remote HPC."""
        if not self.hpc_config.get('enabled'):
            self.logger.info("HPC management is disabled in configuration.")
            return

        host = self.hpc_config.get('host')
        port = self.hpc_config.get('port', 22)
        user = self.hpc_config.get('user')
        key_path = self.hpc_config.get('ssh_key_path')

        if not all([host, user, key_path]):
            self.logger.error("HPC configuration is missing host, user, or ssh_key_path.")
            return

        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.logger.info(f"Connecting to remote HPC at {user}@{host}:{port}...")
            self.ssh_client.connect(hostname=host, port=port, username=user, key_filename=os.path.expanduser(key_path))
            self.logger.info("Successfully connected to remote HPC.")
        except Exception as e:
            self.logger.error(f"Failed to establish SSH connection to HPC: {e}")
            self.ssh_client = None
        
    def _initialize_processes(self) -> None:
        """Initialize process information for enabled processes."""
        for name, process_config in self.config['processes'].items():
            if process_config.get('enabled', True):
                if name not in self.PROCESS_MODULES:
                    self.logger.warning(f"Unknown process type: {name}")
                    continue
                    
                self.processes[name] = ProcessInfo(name, process_config)
                
    def _start_process(self, process_info: ProcessInfo) -> None:
        """
        Start a worker process, either locally or remotely.
        
        Args:
            process_info: Information about the process to start
        """
        is_remote = self.hpc_config.get('enabled', False) and process_info.config.get('remote', False)
        
        if is_remote:
            self._start_remote_process(process_info)
        else:
            self._start_local_process(process_info)
            
    def _start_local_process(self, process_info: ProcessInfo) -> None:
        """Start a process on the local machine."""
        try:
            config_path = self.config.get('config_file_path')
            if not config_path:
                self.logger.critical(f"Config path missing for process {process_info.name}. Aborting start.")
                return

            # Build command to start the process, passing config_path as an argument
            cmd = [
                sys.executable,  # python3
                '-m', self.PROCESS_MODULES[process_info.name],
                config_path
            ]
            
            # No longer need to set environment variables for config
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            process_info.remote_pid = process.pid
            
            self.logger.info(f"Started local process {process_info.name} with PID {process.pid}")
            
        except Exception as e:
            self.logger.error(f"Failed to start local process {process_info.name}: {e}")
            process_info.remote_pid = None
            
    def _start_remote_process(self, process_info: ProcessInfo) -> None:
        """Start a process on the remote HPC."""
        if not self.ssh_client:
            self.logger.error(f"Cannot start remote process {process_info.name}, SSH client not available.")
            return

        try:
            remote_command = process_info.config.get('remote_command')
            if not remote_command:
                self.logger.error(f"No remote_command specified for remote process {process_info.name}")
                return

            # Use nohup to run the process in the background and capture PID
            full_command = f"nohup {remote_command} > /dev/null 2>&1 & echo $!"
            
            stdin, stdout, stderr = self.ssh_client.exec_command(full_command)
            pid_str = stdout.read().decode().strip()
            
            if pid_str.isdigit():
                process_info.remote_pid = int(pid_str)
                self.logger.info(f"Started remote process {process_info.name} with PID {process_info.remote_pid}")
            else:
                error_output = stderr.read().decode().strip()
                self.logger.error(f"Failed to get PID for remote process {process_info.name}. Error: {error_output}")

        except Exception as e:
            self.logger.error(f"Failed to start remote process {process_info.name}: {e}")
            process_info.remote_pid = None
            
    def _stop_process(self, process_info: ProcessInfo, timeout: int = 10) -> None:
        """
        Stop a worker process gracefully, either locally or remotely.
        
        Args:
            process_info: Information about the process to stop
            timeout: Timeout in seconds for graceful termination
        """
        is_remote = self.hpc_config.get('enabled', False) and process_info.config.get('remote', False)

        if is_remote:
            self._stop_remote_process(process_info, timeout)
        else:
            self._stop_local_process(process_info, timeout)

    def _stop_local_process(self, process_info: ProcessInfo, timeout: int):
        """Stop a local process."""
        if process_info.remote_pid is None:
            self.logger.debug(f"Process {process_info.name} is not running")
            return
            
        try:
            import psutil
            proc = psutil.Process(process_info.remote_pid)
            self.logger.info(f"Stopping local process {process_info.name} (PID {process_info.remote_pid})")
            proc.terminate()
            
            try:
                proc.wait(timeout=timeout)
            except psutil.TimeoutExpired:
                self.logger.warning(f"Process {process_info.name} did not terminate, killing")
                proc.kill()
                proc.wait()
        except psutil.NoSuchProcess:
            self.logger.debug(f"Process {process_info.name} already stopped")
        except Exception as e:
            self.logger.error(f"Error stopping process {process_info.name}: {e}")
        finally:
            process_info.remote_pid = None
            
    def _stop_remote_process(self, process_info: ProcessInfo, timeout: int):
        """Stop a remote process."""
        if not self.ssh_client or process_info.remote_pid is None:
            self.logger.debug(f"Remote process {process_info.name} is not running or SSH client not available")
            return

        try:
            # First try SIGTERM for graceful shutdown
            self.logger.info(f"Stopping remote process {process_info.name} (PID {process_info.remote_pid})")
            stdin, stdout, stderr = self.ssh_client.exec_command(f"kill {process_info.remote_pid}")
            
            # Wait for a bit
            time.sleep(timeout / 2)
            
            # Check if still running
            if process_info.is_running(self.ssh_client):
                self.logger.warning(f"Process {process_info.name} did not respond to SIGTERM, forcing kill")
                stdin, stdout, stderr = self.ssh_client.exec_command(f"kill -9 {process_info.remote_pid}")
                
            self.logger.info(f"Process {process_info.name} stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error stopping remote process {process_info.name}: {e}")
        finally:
            process_info.remote_pid = None
            
    def start_all_processes(self) -> None:
        """Start all enabled worker processes."""
        with self._lock:
            self.logger.info("Starting all worker processes...")
            
            for process_info in self.processes.values():
                if not process_info.is_running():
                    self._start_process(process_info)
                    
            self.logger.info(f"Started {len(self.processes)} worker processes")
        
    def stop_all_processes(self) -> None:
        """Stop all worker processes."""
        with self._lock:
            self.logger.info("Stopping all worker processes...")
            
            for process_info in self.processes.values():
                if process_info.is_running():
                    self._stop_process(process_info)
                    
            self.logger.info("All worker processes stopped")
        
    def restart_process(self, process_name: str) -> None:
        """
        Restart a specific worker process.
        
        Args:
            process_name: Name of the process to restart
            
        Raises:
            ValueError: If process name is not known
        """
        with self._lock:
            if process_name not in self.processes:
                raise ValueError(f"Unknown process: {process_name}")
                
            process_info = self.processes[process_name]
            
            self.logger.info(f"Restarting process {process_name}")
            
            # Stop the process if running
            if process_info.is_running():
                self._stop_process(process_info)
                
            # Brief pause before restart
            time.sleep(1)
            
            # Start the process
            self._start_process(process_info)
            
            # Update restart tracking
            process_info.restart_count += 1
            process_info.last_restart = time.time()
        
    def get_process_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status information for all managed processes.
        
        Returns:
            Dictionary mapping process names to status information
        """
        with self._lock:
            status = {}
            
            for name, process_info in self.processes.items():
                # Create config summary with only non-sensitive values
                config_summary = {
                    'enabled': process_info.config.get('enabled', True),
                    'max_restart_attempts': process_info.config.get('max_restart_attempts', 10),
                    'restart_on_failure': process_info.config.get('restart_on_failure', True),
                    'restart_delay_sec': process_info.config.get('restart_delay_sec', 30)
                }
                
                process_status = {
                    'name': name,
                    'running': process_info.is_running(),
                    'pid': process_info.process.pid if process_info.process else None,
                    'restart_count': process_info.restart_count,
                    'last_restart': datetime.fromtimestamp(process_info.last_restart).isoformat() 
                                   if process_info.last_restart else None,
                    'config_summary': config_summary
                }
                status[name] = process_status
                
            return status
        
    def check_process_health(self) -> None:
        """
        Check health of all processes and restart failed ones using exponential backoff.
        
        This method should be called periodically to ensure process health.
        """
        with self._lock:
            for name, process_info in self.processes.items():
                if process_info.process and not process_info.is_running():
                    # Process has failed
                    exit_code = process_info.process.returncode
                    process_info.consecutive_failures += 1
                    
                    self.logger.warning(f"Process {name} failed with exit code {exit_code} "
                                      f"(consecutive_failures: {process_info.consecutive_failures})")
                    
                    # Check if process should be restarted
                    if not process_info.should_restart():
                        process_info.is_failed_permanently = True
                        self.logger.error(f"Process {name} exceeded maximum restart attempts "
                                        f"({process_info.restart_count}). Marking as permanently failed.")
                        continue
                    
                    # Calculate backoff delay
                    backoff_delay = process_info.get_backoff_delay()
                    
                    if (process_info.last_restart is None or 
                        time.time() - process_info.last_restart > backoff_delay):
                        
                        self.logger.info(f"Restarting failed process {name} "
                                       f"(exit_code: {exit_code}, restart_count: {process_info.restart_count}, "
                                       f"backoff_delay: {backoff_delay:.1f}s)")
                        # Note: restart_process already acquires lock, but RLock allows re-entry
                        self.restart_process(name)
                    else:
                        time_remaining = backoff_delay - (time.time() - process_info.last_restart)
                        self.logger.debug(f"Process {name} restart delayed, waiting {time_remaining:.1f}s more "
                                        f"(exponential backoff: {backoff_delay:.1f}s)")
                
                elif process_info.process and process_info.is_running():
                    # Process is running successfully, reset consecutive failures
                    if process_info.consecutive_failures > 0:
                        self.logger.info(f"Process {name} running successfully, resetting failure count")
                        process_info.consecutive_failures = 0
                    
    def get_resource_usage(self) -> Dict[str, Dict[str, Any]]:
        """
        Get resource usage information for all processes.
        
        Returns:
            Dictionary mapping process names to resource usage
        """
        usage = {}
        
        for name, process_info in self.processes.items():
            is_remote = self.hpc_config.get('enabled', False) and process_info.config.get('remote', False)
            is_running = process_info.is_running(self.ssh_client) if is_remote else process_info.is_running()

            if is_running:
                if is_remote and self.ssh_client:
                    try:
                        # Get remote usage using ps command
                        cmd = f"ps -p {process_info.remote_pid} -o %cpu,%mem,stat,lstart"
                        stdin, stdout, stderr = self.ssh_client.exec_command(cmd)
                        output = stdout.read().decode().strip().split('\n')
                        
                        if len(output) > 1:  # First line is header
                            stats = output[1].split()
                            usage[name] = {
                                'cpu_percent': float(stats[0]),
                                'memory_percent': float(stats[1]),
                                'status': stats[2],
                                'start_time': ' '.join(stats[3:])
                            }
                        else:
                            usage[name] = {'error': 'process_not_found_on_remote'}
                    except Exception as e:
                        self.logger.debug(f"Error getting remote resource usage for {name}: {e}")
                        usage[name] = {'error': str(e)}
                else:
                    try:
                        import psutil
                        ps_process = psutil.Process(process_info.remote_pid)
                        
                        usage[name] = {
                            'cpu_percent': ps_process.cpu_percent(),
                            'memory_mb': ps_process.memory_info().rss / (1024 * 1024),
                            'status': ps_process.status(),
                            'create_time': datetime.fromtimestamp(ps_process.create_time()).isoformat()
                        }
                    except ImportError as e:
                        self.logger.debug(f"psutil not available for resource monitoring: {e}")
                        usage[name] = {'error': 'psutil_not_available'}
                    except Exception as e:
                        self.logger.debug(f"Error getting resource usage for process {name}: {e}")
                        usage[name] = {'error': str(e)}
            else:
                usage[name] = {'status': 'not_running'}
                
        return usage