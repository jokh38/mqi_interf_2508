"""
Database utilities for MQI Communicator system using SQLite.
"""

import sqlite3
import threading
import atexit
import weakref
import logging
from contextlib import contextmanager
from typing import Optional, Set, Dict

from .exceptions import DatabaseError


class DatabaseManager:
    """Thread-safe SQLite database manager."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._connections_lock = threading.Lock()
        self._init_lock = threading.Lock()  # Lock for table initialization
        self._all_connections: Set[sqlite3.Connection] = set()
        self._thread_connections: Dict[int, sqlite3.Connection] = {}
        self._logger: Optional[logging.Logger] = None
        self._tables_initialized = False

        # Register cleanup handler for process termination
        atexit.register(self.close_all)

    @property
    def logger(self) -> logging.Logger:
        """Lazy-loaded logger property."""
        if self._logger is None:
            # Import logger locally to prevent circular dependency
            from .logger import get_logger
            self._logger = get_logger(__name__)
        return self._logger

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            try:
                conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging for better concurrency
                conn.execute("PRAGMA synchronous = NORMAL")  # Faster writes
                conn.execute("PRAGMA temp_store = MEMORY")  # Use memory for temp storage
                conn.execute("PRAGMA busy_timeout = 30000")  # 30 second busy timeout
                conn.row_factory = sqlite3.Row
                self._local.connection = conn

                thread_id = threading.get_ident()

                # Track connection for proper cleanup
                with self._connections_lock:
                    self._all_connections.add(conn)
                    self._thread_connections[thread_id] = conn

                # Set up thread cleanup using weakref callback
                def cleanup_thread_connection(ref):
                    self._cleanup_thread_connection(thread_id)

                # Create weak reference to current thread for cleanup
                thread_ref = weakref.ref(threading.current_thread(), cleanup_thread_connection)
                self._local.thread_ref = thread_ref

                # Initialize required tables if not already done
                self._ensure_required_tables()

            except sqlite3.Error as e:
                raise DatabaseError(f"Failed to connect to database: {e}")

        return self._local.connection

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Transaction failed: {e}")

    @contextmanager
    def cursor(self):
        """Context manager for database cursor."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def execute_query(self, query: str, params: Optional[tuple] = None) -> list:
        """
        Execute a SQL query and return results as a list of dictionaries.

        Args:
            query: SQL query string
            params: Optional query parameters

        Returns:
            List of row dictionaries

        Raises:
            DatabaseError: If query execution fails
        """
        try:
            with self.cursor() as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                rows = cursor.fetchall()
                # Convert sqlite3.Row objects to dictionaries
                return [dict(row) for row in rows]

        except sqlite3.Error as e:
            raise DatabaseError(f"Query execution failed: {e}")

    def _ensure_required_tables(self) -> None:
        """Ensure required database tables exist with thread-safe initialization."""
        # Double-checked locking pattern for thread safety
        if self._tables_initialized:
            return

        with self._init_lock:
            # Check again after acquiring lock
            if self._tables_initialized:
                return

            try:
                conn = self._local.connection
                cursor = conn.cursor()

                # Create logs table for logging system
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS logs (
                        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        component TEXT NOT NULL,
                        level TEXT NOT NULL CHECK(level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
                        correlation_id TEXT,
                        message TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Create cases table for workflow management
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS cases (
                        case_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL CHECK(status IN (
                            'NEW', 'QUEUED', 'PROCESSING', 'UPLOADING',
                            'EXECUTING', 'DOWNLOADING', 'COMPLETED', 'FAILED'
                        )),
                        assigned_gpu_id INTEGER,
                        last_updated TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        workflow_step TEXT,
                        error_message TEXT,
                        FOREIGN KEY (assigned_gpu_id) REFERENCES gpu_resources(gpu_id)
                    )
                ''')

                # Create case_history table for audit trail
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS case_history (
                        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        case_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        message TEXT,
                        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                        workflow_step TEXT,
                        gpu_id INTEGER,
                        FOREIGN KEY (case_id) REFERENCES cases(case_id)
                    )
                ''')

                # Create gpu_resources table for resource management
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS gpu_resources (
                        gpu_id INTEGER PRIMARY KEY,
                        uuid TEXT UNIQUE,
                        status TEXT NOT NULL CHECK(status IN ('available', 'reserved', 'error', 'maintenance')),
                        reserved_by_case_id TEXT,
                        last_updated TEXT NOT NULL DEFAULT (datetime('now')),
                        memory_mb INTEGER,
                        utilization_percent REAL,
                        temperature_celsius REAL,
                        FOREIGN KEY (reserved_by_case_id) REFERENCES cases(case_id)
                    )
                ''')

                # Create scanned_cases table for tracking scanned case directories
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS scanned_cases (
                        case_path TEXT PRIMARY KEY,
                        scanned_at TEXT NOT NULL DEFAULT (datetime('now')),
                        status TEXT NOT NULL DEFAULT 'processed' CHECK(status IN ('processed', 'failed'))
                    )
                ''')

                # Create process_status table for tracking running processes
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS process_status (
                        process_name TEXT PRIMARY KEY,
                        pid INTEGER,
                        is_remote BOOLEAN NOT NULL,
                        last_updated TEXT NOT NULL,
                        host TEXT
                    )
                ''')

                conn.commit()
                cursor.close()
                self._tables_initialized = True

            except sqlite3.Error as e:
                raise DatabaseError(f"Failed to create required tables: {e}")

    def _cleanup_thread_connection(self, thread_id: int) -> None:
        """Clean up connection when thread terminates."""
        with self._connections_lock:
            conn = self._thread_connections.pop(thread_id, None)
            if conn:
                self._all_connections.discard(conn)
                try:
                    conn.close()
                    self.logger.debug(f"Successfully closed connection for thread {thread_id}")
                except Exception as e:
                    self.logger.debug(f"Error closing connection for thread {thread_id}: {e}")
                    # Continue with cleanup to prevent resource leaks

    def close(self) -> None:
        """Close database connection for current thread."""
        if hasattr(self._local, 'connection'):
            conn = self._local.connection
            thread_id = threading.get_ident()

            try:
                conn.close()
                self.logger.debug(f"Successfully closed connection for current thread {thread_id}")
            except Exception as e:
                self.logger.debug(f"Error closing connection for thread {thread_id}: {e}")
                # Continue with cleanup to prevent resource leaks

            # Remove from tracking sets
            with self._connections_lock:
                self._all_connections.discard(conn)
                self._thread_connections.pop(thread_id, None)

            delattr(self._local, 'connection')
            if hasattr(self._local, 'thread_ref'):
                delattr(self._local, 'thread_ref')

    def close_all(self) -> None:
        """Close all database connections across all threads."""
        with self._connections_lock:
            connections_to_close = list(self._all_connections)
            self._all_connections.clear()
            self._thread_connections.clear()

        for conn in connections_to_close:
            try:
                conn.close()
            except Exception as e:
                self.logger.debug(f"Error closing connection during shutdown: {e}")
                # Continue closing other connections

    def get_scanned_cases(self) -> Set[str]:
        """
        Load all processed case paths from the database.

        Returns:
            Set of case paths that have been successfully scanned

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            query = "SELECT case_path FROM scanned_cases WHERE status = 'processed'"
            rows = self.execute_query(query)
            return {row['case_path'] for row in rows}
        except Exception as e:
            raise DatabaseError(f"Failed to load scanned cases: {e}")

    def add_scanned_case(self, case_path: str, status: str = 'processed') -> None:
        """
        Add a case path to the scanned cases table.

        Args:
            case_path: The path of the case that was scanned
            status: Status of the scan ('processed' or 'failed')

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO scanned_cases (case_path, status, scanned_at)
                    VALUES (?, ?, datetime('now'))
                """, (case_path, status))
        except Exception as e:
            raise DatabaseError(f"Failed to add scanned case: {e}")

    def remove_scanned_case(self, case_path: str) -> None:
        """
        Remove a case path from the scanned cases table.

        Args:
            case_path: The path of the case to remove

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM scanned_cases WHERE case_path = ?", (case_path,))
        except Exception as e:
            raise DatabaseError(f"Failed to remove scanned case: {e}")