"""
Case Scanner handler module.

This module provides the main logic for handling case scanning and
messaging operations.
"""

import time
from typing import Dict, Any, Set
from src.common.exceptions import ConfigurationError, DatabaseError
from src.common.messaging import MessageQueue
from src.common.logger import get_logger
from src.common.db_utils import DatabaseManager
from src.workers.case_scanner.scanner_service import scan_directory


class CaseScannerHandler:
    """Handler for Case Scanner operations."""
    
    def __init__(self, config: Dict[str, Any], message_queue: MessageQueue):
        """
        Initialize Case Scanner Handler.
        
        Args:
            config: Configuration dictionary
            message_queue: Message queue instance for publishing messages
            
        Raises:
            ConfigurationError: If required configuration is missing
        """
        self.config = config
        self.message_queue = message_queue
        
        # Validate configuration
        if 'scanner' not in config:
            raise ConfigurationError("Missing 'scanner' configuration section")
        
        if 'database' not in config or 'path' not in config['database']:
            raise ConfigurationError("Missing 'database.path' configuration for Case Scanner")
        
        scanner_config = config['scanner']
        
        if 'target_directory' not in scanner_config:
            raise ConfigurationError("Missing 'target_directory' in scanner configuration")
        
        if 'scan_interval_sec' not in scanner_config:
            raise ConfigurationError("Missing 'scan_interval_sec' in scanner configuration")
        
        self.target_directory = scanner_config['target_directory']
        self.scan_interval_sec = scanner_config['scan_interval_sec']
        
        # Initialize database manager for persistent storage
        self.db_manager = DatabaseManager(config['database']['path'])
        
        # Initialize logger with database manager
        self.logger = get_logger('case_scanner', self.db_manager)
        
        # Load known cases from database
        self.known_cases: Set[str] = self._load_known_cases()
        
        self.logger.info(f"Case Scanner initialized - Target: {self.target_directory}, Interval: {self.scan_interval_sec}s, Known cases: {len(self.known_cases)}")
    
    def _load_known_cases(self) -> Set[str]:
        """
        Load known cases from database.
        
        Returns:
            Set of case paths that have been successfully processed
        """
        try:
            return self.db_manager.get_scanned_cases()
        except DatabaseError as e:
            self.logger.error(f"Failed to load known cases from database: {e}")
            self.logger.warning("Starting with empty known cases set due to database error")
            return set()
    
    def process_new_cases(self):
        """
        Process new cases by scanning directory and publishing messages.
        
        This is the main logic function that calls scanner_service.scan()
        and triggers message publishing for each discovered case.
        """
        try:
            new_cases = scan_directory(self.target_directory, self.known_cases)
            
            for case_path in new_cases:
                self._handle_new_case(case_path)
            
            if new_cases:
                self.logger.info(f"Processed {len(new_cases)} new cases")
            
        except Exception as e:
            self.logger.error(f"Error processing new cases from directory '{self.target_directory}': {e}")
            self.logger.debug(f"Case scanner error details - known_cases_count: {len(self.known_cases)}, scan_interval: {self.scan_interval_sec}s")
    
    def _handle_new_case(self, case_path: str):
        """
        Handle a single new case discovery.
        
        Args:
            case_path: Path to the newly discovered case
        """
        self.logger.info(f"New case found: {case_path}")
        
        # Publish new_case_found message
        try:
            correlation_id = self.message_queue.publish_message(
                queue_name='conductor_queue',
                command='new_case_found',
                payload={'case_path': case_path}
            )
        except Exception as e:
            self.logger.error(f"Failed to publish new_case_found message for case '{case_path}': {e}")
            # Mark as failed in database but don't add to known cases
            try:
                self.db_manager.add_scanned_case(case_path, status='failed')
            except DatabaseError as db_e:
                self.logger.error(f"Failed to record failed case in database: {db_e}")
            return
        
        # Add to known cases and persist to database
        self.known_cases.add(case_path)
        
        try:
            self.db_manager.add_scanned_case(case_path, status='processed')
            self.logger.info(f"Published new_case_found message for {case_path} with correlation_id: {correlation_id}")
        except DatabaseError as e:
            self.logger.error(f"Failed to persist scanned case to database: {e}")
            # Keep in memory but log the database failure
    
    def run(self):
        """
        Main execution loop.
        
        Runs the scheduled scanning loop with configured interval.
        """
        self.logger.info("Starting Case Scanner main loop")
        
        try:
            while True:
                self.process_new_cases()
                time.sleep(self.scan_interval_sec)
                
        except KeyboardInterrupt:
            self.logger.info("Case Scanner stopped by user")
        except Exception as e:
            self.logger.error(f"Unexpected error in Case Scanner main loop: {e}")
            raise
        finally:
            # Clean up database connection
            try:
                self.db_manager.close()
            except Exception as e:
                self.logger.error(f"Error closing database during cleanup: {e}")