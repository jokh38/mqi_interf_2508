"""
Main system orchestrator for MQI Communicator system.
Coordinates all worker processes and provides unified system management.
"""

import signal
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.common.config_loader import load_config
from src.common.db_utils import DatabaseManager
from src.common.logger import get_logger
from src.common.logging_setup import setup_logging
from src.common.messaging import MessageBroker
from src.process_manager import ProcessManager
from src.health_monitor import HealthMonitor


class MainOrchestrator:
    """
    Main system orchestrator that manages the entire MQI Communicator system.
    
    Responsibilities:
    - Initialize all system components
    - Start and stop worker processes
    - Monitor system health
    - Handle graceful shutdown
    - Coordinate system-wide operations
    """
    
    def __init__(self, config_file: str):
        """
        Initialize the orchestrator with configuration.
        
        Args:
            config_file: Path to configuration file
        """
        self.config_file = config_file
        self.config = load_config(config_file)
        self.config['config_file_path'] = config_file
        self.db_manager = DatabaseManager(self.config['database']['path'])

        # Re-initialize logging with the db_manager to add the database handler
        setup_logging(level=self.config.get('logging', {}).get('level', 'INFO'), db_manager=self.db_manager)

        self.logger = get_logger(__name__)
        self.logger.info("MainOrchestrator logger initialized with DB handler.")
        
        self.process_manager: Optional[ProcessManager] = None
        self.health_monitor: Optional[HealthMonitor] = None
        self.message_broker: Optional[MessageBroker] = None
        self.running = False
        self.start_time: Optional[datetime] = None
        self.system_monitor_interval = self.config.get('curator', {}).get('monitor_interval_sec', 60)
        self.last_system_monitor_time = 0.0
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
    def start(self) -> None:
        """
        Start the entire MQI Communicator system.
        
        Initializes and starts all worker processes and monitoring systems.
        
        Raises:
            Exception: If system startup fails
        """
        try:
            self.logger.info("Starting MQI Communicator system...")
            
            # Initialize process manager
            self.process_manager = ProcessManager(
                self.config, 
                self.db_manager, 
                self.logger
            )
            
            # Initialize health monitor
            self.health_monitor = HealthMonitor(
                self.config,
                self.db_manager,
                self.logger
            )
            
            # Initialize message broker for system monitoring
            connection_params = {'url': self.config['rabbitmq']['url']}
            self.message_broker = MessageBroker(connection_params, self.config, self.db_manager)
            self.message_broker.connect()
            
            # Start all processes
            self.process_manager.start_all_processes()
            
            # Start health monitoring
            self.health_monitor.start_monitoring()
            
            self.running = True
            self.start_time = datetime.now(timezone.utc)
            
            self.logger.info("MQI Communicator system started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start system: {e}")
            raise
            
    def stop(self) -> None:
        """
        Stop the entire MQI Communicator system.
        
        Gracefully shuts down all worker processes and monitoring systems.
        """
        self.logger.info("Stopping MQI Communicator system...")
        
        # Stop health monitoring first
        if self.health_monitor:
            self.health_monitor.stop_monitoring()
            
        # Stop all worker processes
        if self.process_manager:
            self.process_manager.stop_all_processes()
            
        # Close message broker connection
        if self.message_broker:
            self.message_broker.close()
            
        self.running = False
        self.logger.info("MQI Communicator system stopped successfully")
        
    def restart(self) -> None:
        """
        Restart the entire MQI Communicator system.
        
        Performs a graceful stop followed by a fresh start.
        """
        self.logger.info("Restarting MQI Communicator system...")
        self.stop()
        restart_wait_time = self.config.get('orchestrator', {}).get('restart_wait_time', 1)
        time.sleep(restart_wait_time)  # Configurable pause between stop and start
        self.start()
        self.logger.info("MQI Communicator system restarted successfully")
        
    def run(self) -> None:
        """
        Run the orchestrator in blocking mode.
        
        Starts the system and blocks until shutdown signal is received.
        Handles graceful shutdown on SIGTERM or SIGINT.
        """
        self.start()
        
        try:
            # Block until shutdown signal received
            while self.running:
                current_time = time.time()
                
                # Check if it's time to send system_monitor message
                if self.message_broker and current_time - self.last_system_monitor_time >= self.system_monitor_interval:
                    try:
                        queue_name = self.config.get('queues', {}).get('system_curator', 'system_curator_queue')
                        self.message_broker.publish(
                            queue_name=queue_name,
                            command='system_monitor',
                            payload={'triggered_by': 'orchestrator', 'timestamp': current_time}
                        )
                        self.last_system_monitor_time = current_time
                        self.logger.debug(f"Sent system_monitor message to {queue_name}")
                    except Exception as e:
                        self.logger.error(f"Failed to send system_monitor message: {e}")
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received, stopping system...")
            
        finally:
            self.stop()
            
    def get_status(self) -> Dict[str, Any]:
        """
        Get current system status information.
        
        Returns:
            Dictionary containing system status details
        """
        status: Dict[str, Any] = {
            'running': self.running,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'config_file': self.config_file
        }
        
        # Add process and health monitor status if available
        if self.process_manager:
            status['processes'] = self.process_manager.get_process_status()
            
        if self.health_monitor:
            status['health'] = self.health_monitor.get_health_status()
            
        return status
        
    def _signal_handler(self, signum: int, frame) -> None:
        """
        Handle shutdown signals.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        self.logger.info("Received shutdown signal, stopping system...")
        self.stop()


def main():
    """Entry point for command-line execution."""
    import sys
    import logging

    # Setup basic console logging immediately.
    # This will be enhanced with a DB handler once the orchestrator loads the config.
    setup_logging(level='INFO')
    
    if len(sys.argv) < 2:
        logging.error("Usage: python3 -m src.main_orchestrator <config_file>")
        sys.exit(1)
        
    config_file = sys.argv[1]
    orchestrator = None
    
    try:
        orchestrator = MainOrchestrator(config_file)
        orchestrator.run()
    except KeyboardInterrupt:
        logging.info("Shutdown requested by user, exiting...")
    except Exception as e:
        # The logger should be configured by now, so we can use it directly.
        logging.critical(f"A critical error occurred: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if orchestrator and orchestrator.running:
            logging.info("System shutting down in finally block.")
            orchestrator.stop()


if __name__ == "__main__":
    main()