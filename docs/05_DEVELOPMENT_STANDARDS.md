# 5. Development Standards

This document outlines the standardized development practices for the MQI Communicator project. Adherence to these standards is mandatory for all new contributions to ensure the codebase remains consistent, maintainable, and robust.

## 5.1. Coding Style and Conventions

*   **Style Guide:** All Python code must adhere to the [PEP 8 Style Guide](https://www.python.org/dev/peps/pep-0008/).
*   **Code Formatting:** Code is automatically formatted using `black`. Before committing, ensure your code is formatted by running `black .` from the project root.
*   **Linting:** Code quality is checked using `ruff`. Ensure your code is free of linting errors by running `ruff check .` from the project root.
*   **Type Hinting:** All new functions and methods must include type hints for their arguments and return values, as specified in PEP 484.
*   **Naming Conventions:**
    *   `snake_case` for variables, functions, and methods.
    *   `PascalCase` for classes.
    *   `UPPER_SNAKE_CASE` for constants.
*   **Docstrings:** All modules, classes, and functions must have a docstring explaining their purpose, arguments, and return values.

## 5.2. Test-Driven Development (TDD) Strategy

A Test-Driven Development approach is required for all new features and bug fixes.

### Core Workflow
The development process must follow the **Red-Green-Refactor** cycle:
1.  **Red:** Write a failing test that clearly defines the desired functionality or reproduces the bug.
2.  **Green:** Write the minimum amount of code necessary to make the test pass.
3.  **Refactor:** Clean up and improve the design of the code you just wrote, ensuring all tests continue to pass.

### Test Structure
*   All tests must reside in the `tests/` directory.
*   The test directory structure must mirror the `src/` directory structure.
*   **Unit Tests (`tests/unit/`)**: Test a single class or function in complete isolation. All external dependencies (database, message queue, network, filesystem) **must** be mocked.
*   **Integration Tests (`tests/integration/`)**: Test the interaction between multiple internal components. These tests should use a real, in-memory SQLite database but mock external network services.

### Tooling
*   **Test Runner:** `pytest`
*   **Mocking:** `pytest-mock` (a wrapper for `unittest.mock`)
*   **Coverage:** `pytest-cov`. Run tests with `pytest --cov=src` to measure test coverage. Contributions should not decrease overall test coverage.

## 5.3. Unified Logging and Error Handling Strategy

A consistent strategy for logging and error handling is critical for a distributed system.

### Logging
*   **Automatic Correlation ID:** A `correlation_id` is automatically attached to all log records generated within the context of a message-driven workflow. This is handled by a `contextvars`-based logging filter. Developers do not need to pass the `correlation_id` manually.
*   **Log Levels:** Use appropriate log levels:
    *   `DEBUG`: Detailed information for diagnosing problems.
    *   `INFO`: Confirmation that things are working as expected.
    *   `WARNING`: An indication that something unexpected happened, but the software is still working as expected.
    *   `ERROR`: A serious problem has occurred, and the software was unable to perform some function. This should be used when catching an exception.
    *   `CRITICAL`: A very serious error, indicating that the program itself may be unable to continue running.
*   **Stack Traces:** When logging a caught exception, **always** use `exc_info=True` to ensure the full stack trace is captured in the logs. Example: `logger.error("Something went wrong", exc_info=True)`.

### Error Handling
*   **Use Custom Exceptions:** Always raise specific, custom exceptions defined in `src/common/exceptions.py` (e.g., `RemoteExecutionError`, `DataIntegrityError`) instead of generic `Exception`.
*   **Standard Handler Pattern:** All message-driven workers must implement a standard `try...except` pattern in their main message callback function. This pattern ensures that expected errors are handled gracefully, unexpected errors are caught, and appropriate failure messages are published.
*   **Standardized Failure Messages:** All failure messages published back to the `conductor_queue` must conform to the following standard JSON payload:
    ```json
    {
      "case_id": "<string>",
      "error_type": "string",
      "error_message": "string",
      "original_payload": {}
    }
    ```
*   **Dead Letter Queues (DLQs):** The message broker is configured with DLQs as a safety net. If a message fails processing after all automatic retries, it is routed to a DLQ. The operations team must monitor these queues, as a growing DLQ indicates a persistent, unrecoverable error in a worker.
