import sqlite3
import subprocess
from datetime import datetime
from typing import Optional

def get_gpu_info() -> list[dict]:
    """
    Dynamically detect GPUs and their information using nvidia-smi.
    Returns a list of dictionaries containing GPU information.
    """
    try:
        result = subprocess.run([
            'nvidia-smi', 
            '--query-gpu=gpu_id,gpu_uuid,name,compute_capability,memory.total',
            '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, check=True)
        
        gpus = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                gpu_id, uuid, name, compute_cap, memory = line.strip().split(', ')
                gpus.append({
                    'gpu_id': int(gpu_id),
                    'uuid': uuid,
                    'name': name,
                    'compute_capability': compute_cap,
                    'memory_total_mb': int(float(memory))
                })
        print(f"Detected {len(gpus)} GPUs in the system")
        return gpus
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"Warning: Could not detect GPUs automatically: {e}")
        return []

def initialize_gpu_resources():
    try:
        conn = sqlite3.connect('data/mqi_system_dev.db')
        cursor = conn.cursor()
        
        # Try to detect GPUs automatically
        gpus = get_gpu_info()
        if not gpus:
            # Fallback to manual configuration if detection fails
            print("Warning: No GPUs detected, using default configuration")
            gpus = [{'gpu_id': i, 
                    'uuid': f'GPU-{i:08x}-0000-0000-0000-000000000000', 
                    'name': 'Unknown GPU',
                    'compute_capability': 'unknown', 
                    'memory_total_mb': 0} 
                   for i in range(8)]
        
        # Initialize detected GPUs
        for gpu in gpus:
            cursor.execute("""
                INSERT INTO gpu_resources 
                (gpu_id, uuid, status, last_updated, name, compute_capability, memory_total_mb)
                VALUES (?, ?, 'available', ?, ?, ?, ?)
                ON CONFLICT(gpu_id) DO UPDATE SET
                uuid=excluded.uuid,
                status='available',
                last_updated=excluded.last_updated,
                name=excluded.name,
                compute_capability=excluded.compute_capability,
                memory_total_mb=excluded.memory_total_mb
            """, (
                gpu['gpu_id'],
                gpu['uuid'],
                datetime.now().isoformat(),
                gpu['name'],
                gpu['compute_capability'],
                gpu['memory_total_mb']
            ))
        
        conn.commit()
        print("GPU resources initialized successfully")
        
        # Verify initialization
        cursor.execute("SELECT gpu_id, status, last_updated FROM gpu_resources")
        print("\nInitialized GPU resources:")
        for row in cursor.fetchall():
            print(f"GPU {row[0]}: {row[1]} (Updated: {row[2]})")
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    initialize_gpu_resources()
