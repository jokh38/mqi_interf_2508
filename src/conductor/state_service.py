"""
State Service for Conductor module.

Handles all database operations for case and resource management,
ensuring data consistency through proper transaction handling.
"""

from datetime import datetime
from typing import Optional
from src.common.db_utils import DatabaseManager
from src.common.exceptions import ResourceUnavailableError


class StateService:
    """Encapsulates all database interactions for the Conductor."""
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize StateService with database manager.
        
        Args:
            db_manager: DatabaseManager instance for database operations
        """
        self.db_manager = db_manager
    
    def is_new_case(self, case_id: str) -> bool:
        """
        Check if a case is new (doesn't exist in database).
        
        Args:
            case_id: Unique identifier for the case
            
        Returns:
            True if case doesn't exist, False if it exists
        """
        with self.db_manager.cursor() as cursor:
            cursor.execute("SELECT 1 FROM cases WHERE case_id = ?", (case_id,))
            return cursor.fetchone() is None
    
    def update_case_status(self, case_id: str, new_status: str, message: Optional[str] = None, workflow_step: Optional[str] = None):
        """
        Update case status and workflow step, record in history within a transaction.
        
        Creates new case if it doesn't exist, updates existing case otherwise.
        
        Args:
            case_id: Unique identifier for the case
            new_status: New status to set
            message: Optional message for history record
            workflow_step: Optional workflow step to set
        """
        timestamp = datetime.now().isoformat()
        
        with self.db_manager.transaction() as conn:
            # Check if case exists
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM cases WHERE case_id = ?", (case_id,))
            exists = cursor.fetchone() is not None
            
            if exists:
                # Update existing case
                if workflow_step is not None:
                    cursor.execute(
                        "UPDATE cases SET status = ?, workflow_step = ?, last_updated = ? WHERE case_id = ?",
                        (new_status, workflow_step, timestamp, case_id)
                    )
                else:
                    cursor.execute(
                        "UPDATE cases SET status = ?, last_updated = ? WHERE case_id = ?",
                        (new_status, timestamp, case_id)
                    )
            else:
                # Create new case
                cursor.execute(
                    "INSERT INTO cases (case_id, status, last_updated, workflow_step) VALUES (?, ?, ?, ?)",
                    (case_id, new_status, timestamp, workflow_step)
                )
            
            # Add history record
            cursor.execute(
                "INSERT INTO case_history (case_id, status, message, timestamp, workflow_step) VALUES (?, ?, ?, ?, ?)",
                (case_id, new_status, message, timestamp, workflow_step)
            )
            
            cursor.close()
    
    def reserve_available_gpu(self, case_id: str) -> int:
        """
        Reserve an available GPU for a case within a transaction.
        
        Args:
            case_id: Case ID that will use the GPU
            
        Returns:
            GPU ID that was reserved
            
        Raises:
            ResourceUnavailableError: If no GPUs are available
        """
        # First check if GPUs are available outside transaction
        with self.db_manager.cursor() as cursor:
            cursor.execute(
                "SELECT gpu_id FROM gpu_resources WHERE status = 'available' LIMIT 1"
            )
            result = cursor.fetchone()
            
            if result is None:
                raise ResourceUnavailableError("No GPUs available for reservation")
            
            gpu_id = result['gpu_id']
        
        # Now perform the reservation in transaction
        with self.db_manager.transaction() as conn:
            cursor = conn.cursor()
            
            # Ensure case exists in cases table (or create it with QUEUED status)
            cursor.execute("SELECT 1 FROM cases WHERE case_id = ?", (case_id,))
            if cursor.fetchone() is None:
                timestamp = datetime.now().isoformat()
                cursor.execute(
                    "INSERT INTO cases (case_id, status, last_updated) VALUES (?, ?, ?)",
                    (case_id, "QUEUED", timestamp)
                )
            
            # Double-check and reserve the GPU (race condition protection)
            cursor.execute(
                "SELECT gpu_id FROM gpu_resources WHERE gpu_id = ? AND status = 'available'",
                (gpu_id,)
            )
            if cursor.fetchone() is None:
                # GPU was taken by another process
                raise ResourceUnavailableError("GPU became unavailable during reservation")
            
            # Reserve the GPU
            cursor.execute(
                "UPDATE gpu_resources SET status = 'reserved', reserved_by_case_id = ? WHERE gpu_id = ?",
                (case_id, gpu_id)
            )
            
            cursor.close()
            return gpu_id
    
    def release_gpu_for_case(self, case_id: str):
        """
        Release GPU resources reserved by a case.
        
        Args:
            case_id: Case ID to release GPU resources for
        """
        with self.db_manager.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE gpu_resources SET status = 'available', reserved_by_case_id = NULL WHERE reserved_by_case_id = ?",
                (case_id,)
            )
            cursor.close()
    
    def get_case_current_status(self, case_id: str) -> Optional[str]:
        """
        Get the current status of a case.
        
        Args:
            case_id: Unique identifier for the case
            
        Returns:
            Current status of the case, or None if case doesn't exist
        """
        with self.db_manager.cursor() as cursor:
            cursor.execute("SELECT status FROM cases WHERE case_id = ?", (case_id,))
            result = cursor.fetchone()
            return result['status'] if result else None
    
    def get_case_workflow_step(self, case_id: str) -> Optional[str]:
        """
        Get the current workflow step of a case.
        
        Args:
            case_id: Unique identifier for the case
            
        Returns:
            Current workflow step of the case, or None if case doesn't exist or no workflow step set
        """
        with self.db_manager.cursor() as cursor:
            cursor.execute("SELECT workflow_step FROM cases WHERE case_id = ?", (case_id,))
            result = cursor.fetchone()
            return result['workflow_step'] if result else None