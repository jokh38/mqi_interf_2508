"""
Health monitor for MQI Communicator system.
Monitors system and service health, generates alerts.
"""

import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import pika
    PIKA_AVAILABLE = True
except ImportError:
    PIKA_AVAILABLE = False


class HealthMonitor:
    """
    System health monitor for MQI Communicator.
    
    Responsibilities:
    - Monitor database connectivity and performance
    - Monitor message queue health and throughput
    - Monitor system resource utilization
    - Generate alerts when thresholds are exceeded
    - Provide health status information
    """
    
    def __init__(self, config: Dict[str, Any], db_manager, logger):
        """
        Initialize health monitor.
        
        Args:
            config: System configuration
            db_manager: Database manager instance
            logger: Logger instance
        """
        self.config = config
        self.db_manager = db_manager
        self.logger = logger
        
        # Health check configuration
        health_config = config.get('health', {})
        self.check_interval = health_config.get('check_interval_sec', 60)
        self.alert_thresholds = health_config.get('alert_thresholds', {
            'cpu_percent': 80,
            'memory_percent': 85,
            'disk_percent': 90,
            'queue_depth': 1000
        })
        
        # Monitoring state
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.last_health_status: Optional[Dict[str, Any]] = None
        self._db_counter_lock = threading.Lock()
        self._db_check_counter: int = 0
        
    def start_monitoring(self) -> None:
        """Start health monitoring in background thread."""
        if self.monitoring:
            self.logger.warning("Health monitoring already started")
            return
            
        self.logger.info("Starting health monitoring...")
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
    def stop_monitoring(self) -> None:
        """Stop health monitoring."""
        if not self.monitoring:
            self.logger.debug("Health monitoring not running")
            return
            
        self.logger.info("Stopping health monitoring...")
        self.monitoring = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
            if self.monitor_thread.is_alive():
                self.logger.warning("Health monitoring thread did not stop cleanly")
                
    def get_health_status(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest health status.
        
        Returns:
            Latest health status or None if not available
        """
        return self.last_health_status
        
    def _monitoring_loop(self) -> None:
        """Main monitoring loop that runs in background thread."""
        self.logger.info(f"Health monitoring started with {self.check_interval}s interval")
        
        while self.monitoring:
            try:
                # Run health checks
                health_status = self._run_health_checks()
                self.last_health_status = health_status
                
                # Log overall status
                if health_status['overall']:
                    self.logger.debug("System health check: All systems healthy")
                else:
                    self.logger.warning("System health check: Issues detected")
                    
            except Exception as e:
                self.logger.error(f"Error during health check: {e}")
                
            # Sleep until next check, but check for shutdown signal frequently
            elapsed = 0
            sleep_increment = 1
            while elapsed < self.check_interval and self.monitoring:
                time.sleep(sleep_increment)
                elapsed += sleep_increment
            
        self.logger.info("Health monitoring stopped")
        
    def _run_health_checks(self) -> Dict[str, Any]:
        """
        Run all health checks and return status.
        
        Returns:
            Dictionary containing health status for all components
        """
        timestamp = datetime.utcnow().isoformat()
        
        # Run individual health checks
        db_healthy = self._check_database_health()
        rabbitmq_healthy = self._check_rabbitmq_health()
        system_healthy = self._check_system_health()
        
        # Overall health is True only if all components are healthy
        overall_healthy = db_healthy and rabbitmq_healthy and system_healthy
        
        return {
            'database': db_healthy,
            'rabbitmq': rabbitmq_healthy,
            'system': system_healthy,
            'overall': overall_healthy,
            'timestamp': timestamp
        }
        
    def _check_database_health(self) -> bool:
        """
        Check database connectivity and performance.
        
        Returns:
            True if database is healthy, False otherwise
        """
        try:
            # Simple connectivity test
            result = self.db_manager.execute_query("SELECT 1 as test")
            return len(result) > 0 and result[0].get('test') == 1
            
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return False
            
    def _check_rabbitmq_health(self) -> bool:
        """
        Check RabbitMQ connectivity and performance.
        
        Returns:
            True if RabbitMQ is healthy, False otherwise
        """
        if not PIKA_AVAILABLE:
            self.logger.debug("Pika not available, skipping RabbitMQ health check")
            return True
            
        try:
            rabbitmq_config = self.config.get('rabbitmq', {})
            connection_url = rabbitmq_config.get('url', 'amqp://localhost')
            
            # Test connection
            parameters = pika.URLParameters(connection_url)
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            
            # Test basic functionality by declaring a temporary queue
            queue_result = channel.queue_declare(queue='', exclusive=True)
            temp_queue = queue_result.method.queue
            channel.queue_delete(queue=temp_queue)
            
            connection.close()
            return True
            
        except Exception:
            self.logger.exception("RabbitMQ health check failed")
            return False
            
    def _check_system_health(self) -> bool:
        """
        Check system resource utilization.
        
        Returns:
            True if system resources are healthy, False otherwise
        """
        if not PSUTIL_AVAILABLE:
            self.logger.debug("psutil not available, skipping system health check")
            return True
            
        try:
            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_threshold = self.alert_thresholds.get('cpu_percent', 80)
            
            if cpu_percent > cpu_threshold:
                self.logger.warning(f"High CPU usage: {cpu_percent}% (threshold: {cpu_threshold}%)")
                return False
                
            # Check memory usage
            memory = psutil.virtual_memory()
            memory_threshold = self.alert_thresholds.get('memory_percent', 85)
            
            if memory.percent > memory_threshold:
                self.logger.warning(f"High memory usage: {memory.percent}% (threshold: {memory_threshold}%)")
                return False
                
            # Check disk usage for configured monitor paths
            monitor_paths = self.config.get('health_monitor', {}).get('monitor_paths', ['/'])
            disk_threshold = self.alert_thresholds.get('disk_percent', 90)
            
            for path in monitor_paths:
                try:
                    disk = psutil.disk_usage(path)
                    if disk.percent > disk_threshold:
                        self.logger.warning(f"High disk usage on {path}: {disk.percent}% (threshold: {disk_threshold}%)")
                        return False
                except Exception as e:
                    self.logger.warning(f"Could not check disk usage for path {path}: {e}")
                    continue
                
            return True
            
        except Exception as e:
            self.logger.error(f"System health check failed: {e}")
            return False
            
    def get_detailed_health_info(self) -> Dict[str, Any]:
        """
        Get detailed health information including metrics.
        
        Returns:
            Detailed health information dictionary
        """
        health_info = {
            'timestamp': datetime.utcnow().isoformat(),
            'database': self._get_database_metrics(),
            'rabbitmq': self._get_rabbitmq_metrics(),
            'system': self._get_system_metrics()
        }
        
        return health_info
        
    def _get_database_metrics(self) -> Dict[str, Any]:
        """Get database performance metrics using lightweight queries."""
        try:
            # Basic database metrics
            metrics: Dict[str, Any] = {
                'connected': True,
                'response_time_ms': 0
            }
            
            # Use lightweight query for performance test instead of COUNT(*)
            start_time = time.time()
            result = self.db_manager.execute_query("SELECT 1 as test")
            end_time = time.time()
            
            metrics['response_time_ms'] = int((end_time - start_time) * 1000)
            metrics['healthy'] = len(result) > 0 and result[0].get('test') == 1
            
            # Only get record count occasionally (every 10th check) to reduce load
            with self._db_counter_lock:
                self._db_check_counter += 1
                check_counter = self._db_check_counter
                
            if check_counter % 10 == 1:
                try:
                    # Get approximate row count from sqlite_stat1 if available (much faster)
                    stat_result = self.db_manager.execute_query(
                        "SELECT stat FROM sqlite_stat1 WHERE tbl = 'cases' LIMIT 1"
                    )
                    if stat_result:
                        # Parse the first number from the stat string (approximate row count)
                        stat_str: str = stat_result[0].get('stat', '0')
                        case_count = int(stat_str.split()[0]) if stat_str and stat_str.split() else 0
                        metrics['case_count_approx'] = case_count
                    else:
                        # Fallback to exact count only if stat table doesn't exist
                        count_result = self.db_manager.execute_query("SELECT COUNT(*) as count FROM cases")
                        if count_result:
                            metrics['case_count'] = int(count_result[0]['count'])
                except Exception as count_e:
                    self.logger.debug(f"Could not get case count: {count_e}")
                    metrics['case_count_error'] = str(count_e)
            
            return metrics
            
        except Exception as e:
            return {'connected': False, 'error': str(e)}
            
    def _get_rabbitmq_metrics(self) -> Dict[str, Any]:
        """Get RabbitMQ performance metrics."""
        if not PIKA_AVAILABLE:
            return {'available': False, 'reason': 'pika not installed'}
            
        try:
            # Basic RabbitMQ connectivity test
            rabbitmq_config = self.config.get('rabbitmq', {})
            connection_url = rabbitmq_config.get('url', 'amqp://localhost')
            
            start_time = time.time()
            parameters = pika.URLParameters(connection_url)
            connection = pika.BlockingConnection(parameters)
            connection.close()
            end_time = time.time()
            
            return {
                'connected': True,
                'connection_time_ms': (end_time - start_time) * 1000
            }
            
        except Exception as e:
            return {'connected': False, 'error': str(e)}
            
    def _get_system_metrics(self) -> Dict[str, Any]:
        """Get system resource metrics."""
        if not PSUTIL_AVAILABLE:
            return {'available': False, 'reason': 'psutil not installed'}
            
        try:
            # Get disk usage for configured monitor paths
            monitor_paths = self.config.get('health_monitor', {}).get('monitor_paths', ['/'])
            disk_usage = {}
            for path in monitor_paths:
                try:
                    usage = psutil.disk_usage(path)
                    disk_usage[path] = usage.percent
                except Exception as e:
                    disk_usage[path] = f"error: {e}"
            
            return {
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_usage': disk_usage,
                'load_average': psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None,
                'process_count': len(psutil.pids())
            }
            
        except Exception as e:
            return {'available': False, 'error': str(e)}