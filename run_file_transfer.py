#!/usr/bin/env python3
"""
Script to run the File Transfer worker.

Usage:
    python3 run_file_transfer.py

Environment variables:
    MQI_CONFIG_PATH: Path to configuration file (default: config/config.default.yaml)
"""

import os
import sys
from pathlib import Path

def setup_path():
    """Add src to Python path for module imports."""
    current_dir = Path(__file__).parent
    sys.path.insert(0, str(current_dir / 'src'))

def main_wrapper():
    """Main entry point with path setup."""
    setup_path()
    from workers.file_transfer.main import main
    main()

if __name__ == '__main__':
    main_wrapper()