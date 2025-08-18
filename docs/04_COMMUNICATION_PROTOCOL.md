# 4. Communication Protocol

Communication between the microservices in the MQI Communicator system is handled exclusively by a RabbitMQ message broker. This document specifies the message queues, the standard message format, and the schemas for all commands and events.

## 4.1. Message Queues

The system uses a set of named queues to route messages to the appropriate worker.

| Queue Name                | Consumer              | Purpose                                                      |
| ------------------------- | --------------------- | ------------------------------------------------------------ |
| `conductor_queue`         | Conductor             | Receives status updates and events from all workers.         |
| `file_transfer_queue`     | File Transfer Worker  | Receives commands to upload or download files.               |
| `remote_executor_queue`   | Remote Executor Worker| Receives commands to execute shell commands on the remote HPC. |
| `system_curator_queue`    | System Curator Worker | Receives commands to perform periodic resource monitoring.   |
| `archiver_queue`          | Archiver Worker       | Receives commands to perform database maintenance.           |

## 4.2. Standard Message Envelope

All messages published to any queue must conform to a standard JSON envelope structure. This ensures consistency and provides essential metadata for tracing and debugging.

```json
{
  "command": "string",
  "payload": {},
  "timestamp": "string (ISO 8601)",
  "correlation_id": "string (UUID)",
  "retry_count": "integer"
}
```

| Field            | Type    | Description                                                                          |
| ---------------- | ------- | ------------------------------------------------------------------------------------ |
| `command`        | string  | **Required.** The name of the command or event (e.g., `new_case_found`, `execute_command`). |
| `payload`        | object  | **Required.** A JSON object containing the data specific to the command.           |
| `timestamp`      | string  | An ISO 8601 timestamp indicating when the message was created.                       |
| `correlation_id` | string  | A unique ID (UUID) that links all messages within a single workflow.                 |
| `retry_count`    | integer | The number of times this message has been retried. Used for handling transient errors. |

## 4.3. Message Schemas

This section details the expected `payload` for each command.

---

### `new_case_found`
*   **Source:** Case Scanner Worker
*   **Target Queue:** `conductor_queue`
*   **Purpose:** Notifies the Conductor that a new case directory has been discovered.
*   **Payload Schema:**
    ```json
    {
      "case_id": "string"
    }
    ```

---

### `execute_command`
*   **Source:** Conductor
*   **Target Queue:** `remote_executor_queue`
*   **Purpose:** Instructs the Remote Executor to run a shell command.
*   **Payload Schema:**
    ```json
    {
      "case_id": "string",
      "command": "string",
      "gpu_id": "integer",
      "step": "string"
    }
    ```

---

### `execution_succeeded`
*   **Source:** Remote Executor Worker
*   **Target Queue:** `conductor_queue`
*   **Purpose:** Notifies the Conductor that a remote command completed successfully.
*   **Payload Schema:**
    ```json
    {
      "case_id": "string",
      "stdout": "string"
    }
    ```

---

### `execution_failed`
*   **Source:** Remote Executor Worker
*   **Target Queue:** `conductor_queue`
*   **Purpose:** Notifies the Conductor that a remote command failed.
*   **Payload Schema:**
    ```json
    {
      "case_id": "string",
      "error_type": "string",
      "error_message": "string",
      "original_payload": {}
    }
    ```

---

### `upload_case` (Proposed)
*   **Source:** Conductor
*   **Target Queue:** `file_transfer_queue`
*   **Purpose:** Instructs the File Transfer worker to upload a case directory.
*   **Payload Schema:**
    ```json
    {
      "case_id": "string",
      "local_path": "string",
      "remote_path": "string"
    }
    ```

---

### `case_upload_completed`
*   **Source:** File Transfer Worker
*   **Target Queue:** `conductor_queue`
*   **Purpose:** Notifies the Conductor that a case upload has finished.
*   **Payload Schema:**
    ```json
    {
      "case_id": "string",
      "local_path": "string",
      "remote_path": "string"
    }
    ```

---

### `file_transfer_failed`
*   **Source:** File Transfer Worker
*   **Target Queue:** `conductor_queue`
*   **Purpose:** Notifies the Conductor that a file transfer operation failed.
*   **Payload Schema:**
    ```json
    {
      "case_id": "string",
      "error_type": "string",
      "error_message": "string",
      "original_payload": {}
    }
    ```

---

### `system_monitor`
*   **Source:** Main Orchestrator
*   **Target Queue:** `system_curator_queue`
*   **Purpose:** Triggers a resource monitoring cycle.
*   **Payload Schema:**
    ```json
    {
      "triggered_by": "orchestrator",
      "timestamp": "float"
    }
    ```

---

### `archive_data`
*   **Source:** (External Scheduler or Future Component)
*   **Target Queue:** `archiver_queue`
*   **Purpose:** Triggers a database maintenance and backup cycle.
*   **Payload Schema:** `{}` (Empty)
