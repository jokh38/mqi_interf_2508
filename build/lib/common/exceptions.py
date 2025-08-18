"""
Custom exceptions for MQI Communicator system.

This module provides standardized error handling and message formatting
for consistent error reporting across the application.
"""

from typing import Optional, Dict, Any


def format_error_message(
    operation: str,
    error_details: str,
    context: Optional[Dict[str, Any]] = None,
    suggestion: Optional[str] = None
) -> str:
    """
    Create a standardized error message format.

    Args:
        operation: The operation that failed (e.g., "database connection", "file transfer")
        error_details: The specific error details
        context: Optional context information (e.g., {"file": "test.txt", "retry_count": 3})
        suggestion: Optional suggestion for resolving the issue

    Returns:
        Formatted error message

    Example:
        format_error_message(
            operation="file transfer",
            error_details="Permission denied",
            context={"file": "test.txt", "host": "server1"},
            suggestion="Check file permissions and SSH key access"
        )
        # Returns: "File transfer failed: Permission denied (file: test.txt, host: server1). Suggestion: Check file permissions and SSH key access"
    """
    message = f"{operation.capitalize()} failed: {error_details}"

    if context:
        context_parts = [f"{k}: {v}" for k, v in context.items()]
        message += f" ({', '.join(context_parts)})"

    if suggestion:
        message += f". Suggestion: {suggestion}"

    return message


# Common error message helpers
def format_connection_error(service: str, details: str, host: Optional[str] = None) -> str:
    """Format connection-related error messages."""
    context = {"host": host} if host else None
    return format_error_message(
        operation=f"{service} connection",
        error_details=details,
        context=context,
        suggestion="Check network connectivity and service status"
    )


def format_file_operation_error(operation: str, file_path: str, details: str) -> str:
    """Format file operation error messages."""
    return format_error_message(
        operation=f"file {operation}",
        error_details=details,
        context={"file": file_path},
        suggestion="Check file permissions and path validity"
    )


def format_validation_error(item: str, details: str, expected: Optional[str] = None) -> str:
    """Format validation error messages."""
    context = {"expected": expected} if expected else None
    return format_error_message(
        operation=f"{item} validation",
        error_details=details,
        context=context,
        suggestion="Review input parameters and configuration"
    )


class MQIError(Exception):
    """Base exception for the MQI application."""
    pass


class ResourceUnavailableError(MQIError):
    """Raised when a required resource (e.g., GPU) is not available."""
    pass


class RemoteExecutionError(MQIError):
    """Raised when a command fails to execute on a remote worker."""
    pass


class DataIntegrityError(MQIError):
    """Raised on data validation failures (e.g., checksum mismatch)."""
    pass


class NetworkError(MQIError):
    """Raised when network-related errors occur."""
    pass


class ConfigurationError(MQIError):
    """Raised when configuration is invalid or missing."""
    pass


class DatabaseError(MQIError):
    """Raised when database operations fail."""
    pass


class MessagingError(MQIError):
    """Raised when message queue operations fail."""
    pass