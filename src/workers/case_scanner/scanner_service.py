"""
Case Scanner service module.

This module provides functions to scan directories for new cases.
"""

import os
from typing import List, Set
from src.common.exceptions import ConfigurationError


def scan_directory(directory_path: str, known_cases: Set[str]) -> List[str]:
    """
    Scan directory for new cases (directories).
    
    This is a pure function that scans the given directory and returns
    a list of new directory paths that are not in the known_cases set.
    
    Args:
        directory_path: Path to directory to scan
        known_cases: Set of already known case paths
        
    Returns:
        List of new case paths (directories only)
        
    Raises:
        ConfigurationError: If directory doesn't exist or can't be accessed
    """
    if not os.path.exists(directory_path):
        raise ConfigurationError(f"Target directory does not exist: {directory_path}")
    
    if not os.path.isdir(directory_path):
        raise ConfigurationError(f"Target path is not a directory: {directory_path}")
    
    try:
        entries = os.listdir(directory_path)
    except PermissionError:
        raise ConfigurationError(f"Permission denied accessing directory: {directory_path}")
    except Exception as e:
        raise ConfigurationError(f"Error accessing directory {directory_path}: {e}")
    
    new_cases = []
    
    for entry in entries:
        entry_path = os.path.join(directory_path, entry)
        
        # Only consider directories, ignore files
        if _is_new_case_directory(entry_path, known_cases):
            new_cases.append(entry_path)
    
    return new_cases


def _is_new_case_directory(entry_path: str, known_cases: Set[str]) -> bool:
    """
    Check if entry is a new case directory.
    
    Args:
        entry_path: Path to check
        known_cases: Set of already known case paths
        
    Returns:
        True if entry is a new case directory, False otherwise
    """
    return os.path.isdir(entry_path) and entry_path not in known_cases