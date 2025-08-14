#!/usr/bin/env python3
"""
Database Setup Script for MQI Communicator System

This script initializes the SQLite database with the complete schema
including tables, indexes, and initial data required for production.
"""

import os
import sys
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.common.config_loader import load_config
from src.common.exceptions import DatabaseError


class DatabaseSetup:
    """Database initialization and setup manager."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
    
    def connect(self):
        """Establish database connection."""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.execute("PRAGMA foreign_keys = ON")
            print(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to connect to database: {e}")
    
    def create_schema(self):
        """Create complete database schema."""
        print("Creating database schema...")
        
        # Main operational tables
        self._create_cases_table()
        self._create_case_history_table()
        self._create_gpu_resources_table()
        self._create_logs_table()
        self._create_process_status_table()
        
        # Archive tables
        self._create_archived_cases_table()
        self._create_archived_case_history_table()
        
        # Create indexes for performance
        self._create_indexes()
        
        self.connection.commit()
        print("Schema created successfully")
    
    def _create_cases_table(self):
        """Create the cases table."""
        self.connection.execute('''
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
    
    def _create_case_history_table(self):
        """Create the case_history table."""
        self.connection.execute('''
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
    
    def _create_gpu_resources_table(self):
        """Create the gpu_resources table."""
        # Drop existing table if it exists
        self.connection.execute('DROP TABLE IF EXISTS gpu_resources')
        self.connection.execute('''
            CREATE TABLE gpu_resources (
                gpu_id INTEGER PRIMARY KEY,
                uuid TEXT UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('available', 'reserved', 'error', 'maintenance')),
                reserved_by_case_id TEXT,
                last_updated TEXT NOT NULL DEFAULT (datetime('now')),
                gpu_utilization REAL DEFAULT 0.0,
                memory_used_mb INTEGER DEFAULT 0,
                memory_total_mb INTEGER DEFAULT 0,
                temperature_c REAL DEFAULT 0.0,
                name TEXT,
                compute_capability TEXT,
                FOREIGN KEY (reserved_by_case_id) REFERENCES cases(case_id)
            )
        ''')
    
    def _create_logs_table(self):
        """Create the logs table for system logging."""
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                component TEXT NOT NULL,
                level TEXT NOT NULL CHECK(level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
                correlation_id TEXT,
                message TEXT NOT NULL
            )
        ''')

    def _create_process_status_table(self):
        """Create the process_status table."""
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS process_status (
                process_name TEXT PRIMARY KEY,
                pid INTEGER,
                is_remote BOOLEAN NOT NULL,
                last_updated TEXT NOT NULL,
                host TEXT
            )
        ''')
    
    def _create_archived_cases_table(self):
        """Create the archived_cases table."""
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS archived_cases (
                case_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                assigned_gpu_id INTEGER,
                last_updated TEXT NOT NULL,
                created_at TEXT,
                workflow_step TEXT,
                error_message TEXT,
                archived_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')
    
    def _create_archived_case_history_table(self):
        """Create the archived_case_history table."""
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS archived_case_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                timestamp TEXT NOT NULL,
                workflow_step TEXT,
                gpu_id INTEGER,
                archived_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        ''')
    
    def _create_indexes(self):
        """Create database indexes for performance optimization."""
        indexes = [
            # Cases table indexes
            "CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status)",
            "CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_cases_last_updated ON cases(last_updated)",
            "CREATE INDEX IF NOT EXISTS idx_cases_gpu_id ON cases(assigned_gpu_id)",
            
            # Case history indexes
            "CREATE INDEX IF NOT EXISTS idx_case_history_case_id ON case_history(case_id)",
            "CREATE INDEX IF NOT EXISTS idx_case_history_timestamp ON case_history(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_case_history_status ON case_history(status)",
            
            # GPU resources indexes
            "CREATE INDEX IF NOT EXISTS idx_gpu_resources_status ON gpu_resources(status)",
            "CREATE INDEX IF NOT EXISTS idx_gpu_resources_reserved_by ON gpu_resources(reserved_by_case_id)",
            "CREATE INDEX IF NOT EXISTS idx_gpu_resources_last_updated ON gpu_resources(last_updated)",
            
            # Logs table indexes
            "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_logs_component ON logs(component)",
            "CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)",
            
            # Archived tables indexes
            "CREATE INDEX IF NOT EXISTS idx_archived_cases_archived_at ON archived_cases(archived_at)",
            "CREATE INDEX IF NOT EXISTS idx_archived_case_history_case_id ON archived_case_history(case_id)",
            "CREATE INDEX IF NOT EXISTS idx_archived_case_history_archived_at ON archived_case_history(archived_at)"
        ]
        
        for index_sql in indexes:
            self.connection.execute(index_sql)
        
        print("Database indexes created successfully")
    
    def initialize_gpu_resources(self, gpu_count: int = 8):
        """Initialize GPU resources table with available GPUs."""
        print(f"Initializing {gpu_count} GPU resources...")
        
        # Clear existing GPU resources
        self.connection.execute("DELETE FROM gpu_resources")
        
        # Add GPU resources
        timestamp = datetime.now().isoformat()
        for gpu_id in range(gpu_count):
            self.connection.execute('''
                INSERT INTO gpu_resources 
                (gpu_id, status, last_updated, name, memory_total_mb)
                VALUES (?, 'available', ?, ?, ?)
            ''', (gpu_id, timestamp, f"GPU-{gpu_id}", 8192))  # Default 8GB GPUs
        
        self.connection.commit()
        print(f"Initialized {gpu_count} GPU resources")
    
    def verify_schema(self):
        """Verify that all required tables and indexes exist."""
        print("Verifying database schema...")
        
        required_tables = [
            'cases', 'case_history', 'gpu_resources', 'logs',
            'archived_cases', 'archived_case_history'
        ]
        
        cursor = self.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        missing_tables = set(required_tables) - set(existing_tables)
        if missing_tables:
            raise DatabaseError(f"Missing required tables: {missing_tables}")
        
        # Verify indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        existing_indexes = [row[0] for row in cursor.fetchall()]
        print(f"Found {len(existing_indexes)} indexes")
        
        # Verify GPU resources
        cursor.execute("SELECT COUNT(*) FROM gpu_resources")
        gpu_count = cursor.fetchone()[0]
        print(f"GPU resources initialized: {gpu_count} GPUs")
        
        print("Schema verification completed successfully")
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            print("Database connection closed")


def main():
    """Main database setup function."""
    parser = argparse.ArgumentParser(description="Setup MQI Communicator database")
    parser.add_argument('--env', choices=['development', 'production'], 
                       default='development', help='Environment to set up')
    parser.add_argument('--db-path', help='Override database path')
    parser.add_argument('--gpu-count', type=int, default=4, 
                       help='Number of GPU resources to initialize')
    parser.add_argument('--verify-only', action='store_true', 
                       help='Only verify existing schema')
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        if args.db_path:
            db_path = args.db_path
        else:
            config_file = f"config.{args.env}.yaml"
            if not os.path.exists(os.path.join("config", config_file)):
                config_file = "config.default.yaml"
            
            config = load_config(os.path.join("config", config_file))
            db_path = config['database']['path']
        
        # Ensure database directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        
        print(f"Setting up database for {args.env} environment")
        print(f"Database path: {db_path}")
        
        # Initialize database
        db_setup = DatabaseSetup(db_path)
        db_setup.connect()
        
        if not args.verify_only:
            db_setup.create_schema()
            db_setup.initialize_gpu_resources(args.gpu_count)
        
        db_setup.verify_schema()
        db_setup.close()
        
        print(f"Database setup completed successfully for {args.env} environment")
        
    except Exception as e:
        print(f"Database setup failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()