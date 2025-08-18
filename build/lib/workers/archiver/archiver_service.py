"""
Archiver service for moving old data and backing up database.
"""

import os
import subprocess
import datetime
from src.common.db_utils import DatabaseManager
from src.common.exceptions import DatabaseError


def archive_old_data(db_manager: DatabaseManager, retention_days: int) -> None:
    """
    Archive old completed/failed cases to archive tables.

    Args:
        db_manager: Database manager instance
        retention_days: Number of days to retain active cases

    Raises:
        DatabaseError: If database operations fail
    """
    try:

        # Calculate cutoff date
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=retention_days)
        cutoff_date_str = cutoff_date.isoformat()

        with db_manager.transaction() as conn:
            cursor = conn.cursor()

            # Find cases to archive (COMPLETED or FAILED and older than retention period)
            cursor.execute("""
                SELECT case_id, status, assigned_gpu_id, last_updated
                FROM cases
                WHERE status IN ('COMPLETED', 'FAILED')
                AND last_updated < ?
            """, (cutoff_date_str,))

            cases_to_archive = cursor.fetchall()

            if not cases_to_archive:
                return  # No cases to archive

            # Get case IDs for history archiving
            case_ids = [case[0] for case in cases_to_archive]
            case_ids_placeholders = ','.join('?' * len(case_ids))

            # Move cases to archive table
            cursor.execute(f"""
                INSERT INTO archived_cases (case_id, status, assigned_gpu_id, last_updated)
                SELECT case_id, status, assigned_gpu_id, last_updated
                FROM cases
                WHERE case_id IN ({case_ids_placeholders})
            """, case_ids)

            # Move case history to archive table
            cursor.execute(f"""
                INSERT INTO archived_case_history (case_id, status, timestamp)
                SELECT case_id, status, timestamp
                FROM case_history
                WHERE case_id IN ({case_ids_placeholders})
            """, case_ids)

            # Delete from original tables
            cursor.execute(f"""
                DELETE FROM case_history
                WHERE case_id IN ({case_ids_placeholders})
            """, case_ids)

            cursor.execute(f"""
                DELETE FROM cases
                WHERE case_id IN ({case_ids_placeholders})
            """, case_ids)

    except Exception as e:
        raise DatabaseError(f"Failed to archive old data: {e}")


def backup_database(db_manager: DatabaseManager, backup_path: str) -> None:
    """
    Create a backup of the SQLite database using sqlite3 .backup command.

    Args:
        db_manager: Database manager instance
        backup_path: Directory path where backup should be stored

    Raises:
        DatabaseError: If backup operation fails
    """
    db_path = db_manager.db_path
    try:
        # Ensure backup directory exists
        os.makedirs(backup_path, exist_ok=True)

        # Generate timestamped backup filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.db"
        backup_file_path = os.path.join(backup_path, backup_filename)

        # Execute sqlite3 backup command
        result = subprocess.run([
            'sqlite3',
            db_path,
            '.backup',
            backup_file_path
        ], capture_output=True, text=True)

        if result.returncode != 0:
            raise DatabaseError(f"Database backup failed: {result.stderr}")

    except subprocess.CalledProcessError as e:
        raise DatabaseError(f"Database backup command failed: {e}")
    except Exception as e:
        raise DatabaseError(f"Database backup failed: {e}")