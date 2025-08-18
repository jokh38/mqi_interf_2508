# Component Guide: Case Scanner Worker

## 1. Overview

The Case Scanner is the entry point for the entire QA workflow. Its sole responsibility is to monitor a specific directory on the filesystem and detect when new cases (represented as subdirectories) are added.

It is a simple, polling-based worker that runs in an infinite loop.

## 2. Core Responsibilities

*   **Poll Target Directory:** Periodically scans a configured `target_directory` for new subdirectories.
*   **Maintain State:** It keeps a persistent record of all the directories it has already processed to avoid creating duplicate workflows. This state is stored in the `scanned_cases` table in the database.
*   **Publish New Case Events:** When a new, unknown subdirectory is found, it publishes a `new_case_found` message to the `conductor_queue` to trigger the start of a new workflow.

## 3. Workflow

1.  The worker starts and loads the set of already processed directory paths from the `scanned_cases` table into memory.
2.  It enters an infinite loop.
3.  In each loop iteration:
    a. It lists all subdirectories in the `target_directory`.
    b. It compares this list against its in-memory set of known cases.
    c. For each new directory found, it publishes a `new_case_found` message and adds the directory path to its in-memory set and the `scanned_cases` database table.
    d. It sleeps for the configured `scan_interval_sec`.

## 4. Published Messages

The Case Scanner publishes one type of message:

| Command          | Target Queue      | Purpose                                    |
| ---------------- | ----------------- | ------------------------------------------ |
| `new_case_found` | `conductor_queue` | To start a new workflow for a discovered case. |

*   **Payload Schema:**
    ```json
    {
      "case_id": "string" // The name of the new subdirectory
    }
    ```

## 5. Key Configuration Parameters

The Case Scanner's behavior is configured in the `scanner` section of the `config.yaml` file.

```yaml
scanner:
  target_directory: "/path/to/scan"
  scan_interval_sec: 60
  conductor_queue_name: "conductor_queue" # Should match the conductor's queue
```

## 6. Developer Guide

*   **Main Loop:** The main polling logic is in the `run()` method of `src/workers/case_scanner/handler.py`.
*   **Scanning Logic:** The pure function for scanning the directory is located in `src/workers/case_scanner/scanner_service.py`. It is decoupled from any database or messaging logic, making it easy to unit test.
*   **State Management:** The worker's state (known cases) is managed by the `db_manager` instance, which interacts with the `scanned_cases` table.
