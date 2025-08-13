#!/usr/bin/env python3
"""
Quick test script for Remote Executor.

This script demonstrates how to run the Remote Executor worker.
"""

import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from workers.remote_executor.main import main

if __name__ == '__main__':
    print("Starting Remote Executor worker...")
    print("Note: This requires RabbitMQ to be running and properly configured SSH access.")
    print("Press Ctrl+C to stop the worker.")
    print()
    
    try:
        main()
    except Exception as e:
        print(f"Error running Remote Executor: {e}")
        sys.exit(1)