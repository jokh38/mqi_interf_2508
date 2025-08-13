# File: src/dashboard/data_collector.py
"""
DataCollector implementation based on the provided dashboard_plan.md.
This module integrates strictly with the real system components.
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.common.db_utils import DatabaseManager
from src.common.config_loader import load_config
from src.health_monitor import HealthMonitor
from src.process_manager import ProcessManager
from src.workers.system_curator.monitor_service import fetch_gpu_metrics
from src.common.exceptions import RemoteExecutionError
from src.common.remote_executor import RemoteExecutor


class DataCollector:
    """Aggregates data from all system sources for the dashboard."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        db_path = config['database']['path']
        self.db_manager = DatabaseManager(db_path)
        self.health_monitor = HealthMonitor(config, self.db_manager, self.logger)
        self.process_manager = ProcessManager(config, self.db_manager, self.logger)
        self.ssh_config = config.get('ssh', {})
        self.gpu_command = config.get('curator', {}).get('gpu_monitor_command', '')
        self.executor = RemoteExecutor(self.config)

    async def get_system_status(self) -> Dict[str, Any]:
        try:
            health_status = await asyncio.to_thread(self.health_monitor.get_health_status)
            if not health_status:
                return {'overall': 'unknown', 'timestamp': datetime.utcnow().isoformat(), 'uptime_seconds': 0}
            overall_status = 'healthy' if health_status.get('overall', False) else 'warning'
            if not health_status.get('database', True):
                overall_status = 'error'
            return {'overall': overall_status, 'timestamp': health_status.get('timestamp', datetime.utcnow().isoformat()), 'uptime_seconds': int(time.time())}
        except Exception as e:
            self.logger.error(f"Error getting system status: {e}")
            return {'overall': 'error', 'timestamp': datetime.utcnow().isoformat(), 'uptime_seconds': 0}

    async def get_active_jobs(self) -> List[Dict[str, Any]]:
        try:
            query = """
            SELECT case_id, status, assigned_gpu_id, workflow_step, last_updated, created_at
            FROM cases
            WHERE status IN ('QUEUED', 'PROCESSING', 'UPLOADING', 'EXECUTING', 'DOWNLOADING')
            ORDER BY created_at DESC
            LIMIT 50
            """
            rows = await asyncio.to_thread(self.db_manager.execute_query, query)
            return [{
                'case_id': row['case_id'],
                'status': row['status'],
                'workflow_step': row['workflow_step'],
                'assigned_gpu_id': row['assigned_gpu_id'],
                'progress': self._calculate_progress(row['workflow_step']),
                'started_at': row['created_at'],
                'last_updated': row['last_updated']
            } for row in rows]
        except Exception as e:
            self.logger.error(f"Error getting active jobs: {e}")
            return []

    async def get_gpu_metrics(self) -> List[Dict[str, Any]]:
        """
        Fetches GPU metrics from both the database and a live SSH command,
        then merges them. Live data is prioritized.
        """
        db_gpus = []
        try:
            db_gpus = await asyncio.to_thread(self.db_manager.execute_query, """
                SELECT gpu_id, uuid, status, reserved_by_case_id, utilization_percent, 
                       memory_mb as memory_used_mb, temperature_celsius, last_updated
                FROM gpu_resources
                ORDER BY gpu_id
            """)
        except Exception as e:
            self.logger.error(f"Error querying GPU resources from database: {e}")

        live_metrics = []
        if self.ssh_config and self.gpu_command:
            try:
                live_metrics = await asyncio.to_thread(fetch_gpu_metrics, self.config, self.db_manager)
            except (RemoteExecutionError, ImportError, AttributeError) as e:
                self.logger.warning(f"Could not fetch live GPU metrics: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error fetching live GPU metrics: {e}")

        all_gpus: Dict[int, Dict[str, Any]] = {}

        # First, process GPUs from the database
        for db_gpu in db_gpus:
            gpu_id = db_gpu['gpu_id']
            all_gpus[gpu_id] = {
                'gpu_id': gpu_id,
                'utilization': db_gpu.get('utilization_percent', 0),
                'memory_used_mb': db_gpu.get('memory_used_mb', 0),
                'memory_total_mb': db_gpu.get('memory_total_mb', 16384),  # Default, may be overwritten
                'temperature_c': db_gpu.get('temperature_celsius', 0),
                'status': db_gpu.get('status', 'UNKNOWN'),
                'reserved_by': db_gpu.get('reserved_by_case_id'),
                'last_updated': db_gpu.get('last_updated')
            }

        # Then, merge or add live metrics, overwriting with fresher data
        if live_metrics:
            for live_gpu in live_metrics:
                gpu_id = live_gpu['gpu_id']
                live_data = {
                    'name': live_gpu['name'],
                    'utilization': live_gpu['utilization'],
                    'memory_used_mb': live_gpu['memory_used_mb'],
                    'memory_total_mb': live_gpu['memory_total_mb'],
                    'temperature_c': live_gpu['temperature_c'],
                    'last_updated': datetime.utcnow().isoformat()
                }
                
                if gpu_id in all_gpus:
                    all_gpus[gpu_id].update(live_data)
                else:
                    # This GPU is live but not in DB, create a new entry
                    all_gpus[gpu_id] = {
                        'gpu_id': gpu_id,
                        'status': 'ONLINE',  # Not in DB, but seen live
                        'reserved_by': None,
                        **live_data
                    }
        
        if not all_gpus:
            return []

        return sorted(list(all_gpus.values()), key=lambda gpu: gpu['gpu_id'])

    async def get_worker_status(self) -> List[Dict[str, Any]]:
        process_status = await asyncio.to_thread(self.process_manager.get_process_status)
        resource_usage = await asyncio.to_thread(self.process_manager.get_resource_usage)
        workers = []
        for name, status in process_status.items():
            worker_data = {
                'name': name,
                'status': 'running' if status['running'] else 'stopped',
                'pid': status['pid'],
                'uptime_seconds': 0,
                'health': 'healthy' if status['running'] else 'error'
            }
            if name in resource_usage:
                usage = resource_usage[name]
                worker_data.update({
                    'cpu_percent': usage.get('cpu_percent'),
                    'memory_mb': usage.get('memory_mb')
                })
            workers.append(worker_data)
        return workers

    async def get_system_health(self) -> Dict[str, Any]:
        # Fetch health from remote HPC
        remote_health = await self.get_remote_system_health()
        if remote_health:
            return remote_health

        # Fallback to local health if remote fails
        self.logger.warning("Falling back to local system health.")
        health_info = await asyncio.to_thread(self.health_monitor.get_detailed_health_info)
        system_metrics = health_info.get('system', {})
        return {
            'cpu_percent': system_metrics.get('cpu_percent', 0),
            'memory_percent': system_metrics.get('memory_percent', 0),
            'disk_percent': system_metrics.get('disk_percent', 0),
            'load_average': system_metrics.get('load_average'),
            'process_count': system_metrics.get('process_count', 0),
            'timestamp': health_info.get('timestamp')
        }

    async def get_recent_activity(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            rows = await asyncio.to_thread(self.db_manager.execute_query, """
                SELECT case_id, status, message, timestamp, workflow_step
                FROM case_history
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            return [{
                'timestamp': row['timestamp'],
                'case_id': row['case_id'],
                'status': row['status'],
                'message': row['message'] or f"Status changed to {row['status']}",
                'workflow_step': row['workflow_step']
            } for row in rows]
        except Exception as e:
            self.logger.error(f"Error getting recent activity: {e}")
            return []

    async def get_remote_system_health(self) -> Dict[str, Any]:
        """Fetches system health metrics from the remote HPC via SSH."""
        if not self.ssh_config:
            self.logger.warning("SSH config not found, cannot fetch remote system health.")
            return {}

        try:
            # This command fetches CPU, Memory, and Disk usage in a single pass
            command = "top -b -n 1 | grep '%Cpu(s)' | awk '{print $2}' && free | grep Mem | awk '{print $3/$2 * 100.0}' && df -h / | awk 'NR==2 {print $5}'"

            # Since we are executing a raw command, we don't need a specific script path
            stdout, stderr = await asyncio.to_thread(self.executor.execute, command)

            if stderr:
                self.logger.error(f"Error fetching remote system health: {stderr}")
                return {}

            lines = stdout.strip().split('\n')
            if len(lines) < 3:
                self.logger.error(f"Unexpected output from remote health command: {stdout}")
                return {}

            cpu_percent = float(lines[0])
            memory_percent = float(lines[1])
            disk_percent = int(lines[2].replace('%', ''))

            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'disk_percent': disk_percent,
                'timestamp': datetime.utcnow().isoformat()
            }

        except (RemoteExecutionError, ImportError, AttributeError) as e:
            self.logger.warning(f"Could not fetch remote system health: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Unexpected error fetching remote system health: {e}")
            return {}

    def _calculate_progress(self, workflow_step: Optional[str]) -> int:
        if not workflow_step:
            return 0
        return {
            'run_interpreter': 30,
            'run_moqui_sim': 70,
            'convert_to_dicom': 90
        }.get(workflow_step, 10)
