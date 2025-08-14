"""
Database service for System Curator worker.
Handles database operations for updating GPU resource status.
"""

from datetime import datetime
from typing import List, Dict, Any
from src.common.db_utils import DatabaseManager
from src.common.exceptions import DatabaseError
from src.common.logger import get_logger


def update_resource_status(db_manager: DatabaseManager, gpu_metrics: List[Dict[str, Any]]) -> None:
    """
    Update GPU resource status in the database.
    
    Args:
        db_manager: Database manager instance
        gpu_metrics: List of GPU metrics to update
        
    Raises:
        DatabaseError: If database operations fail
    """
    # Initialize logger with database manager
    logger = get_logger(__name__, db_manager)
    
    if not gpu_metrics:
        logger.debug("No GPU metrics to update")
        return
    
    try:
        with db_manager.transaction() as conn:
            cursor = conn.cursor()
            
            current_timestamp = datetime.now().isoformat()
            
            for gpu_data in gpu_metrics:
                gpu_id = gpu_data['gpu_id']
                gpu_uuid = gpu_data.get('uuid')
                
                # Try to find GPU by UUID first, then by ID
                if gpu_uuid:
                    # Try exact UUID match first
                    cursor.execute("SELECT gpu_id FROM gpu_resources WHERE uuid = ?", (gpu_uuid,))
                    row = cursor.fetchone()
                    if row is None and gpu_id is not None:
                        # If no exact match, try by ID
                        cursor.execute("SELECT gpu_id FROM gpu_resources WHERE gpu_id = ?", (gpu_id,))
                        row = cursor.fetchone()
                else:
                    cursor.execute("SELECT gpu_id FROM gpu_resources WHERE gpu_id = ?", (gpu_id,))
                    row = cursor.fetchone()
                    
                if row is None:
                    # If GPU not found, insert a new record
                    logger.info(f"New GPU detected: ID {gpu_id} (UUID: {gpu_uuid}), adding to database.")
                    cursor.execute("""
                        INSERT INTO gpu_resources (gpu_id, uuid, status, gpu_utilization, memory_used_mb, memory_total_mb, temperature_c, last_updated)
                        VALUES (?, ?, 'available', ?, ?, ?, ?, ?)
                    """, (
                        gpu_id,
                        gpu_uuid,
                        gpu_data['utilization'],
                        gpu_data['memory_used_mb'],
                        gpu_data['memory_total_mb'],
                        gpu_data['temperature_c'],
                        current_timestamp
                    ))
                else:
                    # Update existing GPU metrics
                    cursor.execute("""
                        UPDATE gpu_resources
                        SET gpu_utilization = ?,
                            memory_used_mb = ?,
                            memory_total_mb = ?,
                            temperature_c = ?,
                            last_updated = ?,
                            uuid = COALESCE(?, uuid)
                        WHERE gpu_id = ?
                    """, (
                        gpu_data['utilization'],
                        gpu_data['memory_used_mb'],
                        gpu_data['memory_total_mb'],
                        gpu_data['temperature_c'],
                        current_timestamp,
                        gpu_uuid,
                        gpu_id
                    ))
                
                logger.debug(f"Updated GPU {gpu_id} metrics: "
                           f"utilization={gpu_data['utilization']}%, "
                           f"memory={gpu_data['memory_used_mb']}MB, "
                           f"temperature={gpu_data['temperature_c']}°C")
            
            logger.info(f"Successfully updated {len(gpu_metrics)} GPU resource entries")
            
    except Exception as e:
        logger.error(f"Failed to update GPU resource status: {e}")
        raise DatabaseError(f"Database update failed: {e}")