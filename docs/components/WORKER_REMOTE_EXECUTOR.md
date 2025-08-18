# Component Guide: Remote Executor Worker

## 1. Overview

The Remote Executor worker is responsible for executing shell commands on the remote HPC system via SSH. This is the component that performs the core computational work of the QA workflow, such as running simulation scripts.

It is a message-driven worker that listens for `execute_command` messages, runs the specified command, and reports the success or failure of the execution.

## 2. Core Responsibilities

*   **Execute Remote Commands:** Establishes an SSH connection to the remote HPC and executes the shell command provided in the message payload.
*   **Capture Output:** Captures the `stdout`, `stderr`, and `exit_code` of the executed command.
*   **Status Reporting:** Publishes an `execution_succeeded` or `execution_failed` message back to the `Conductor` based on the outcome of the command execution.

## 3. Consumed Messages

The Remote Executor worker listens to the `remote_executor_queue` for one command:

| Command           | Source    | Purpose                               |
| ----------------- | --------- | ------------------------------------- |
| `execute_command` | Conductor | To execute a shell command on the remote HPC. |

*   **Payload Schema:**
    ```json
    {
      "case_id": "string",
      "command": "string", // The full shell command to execute
      "gpu_id": "integer",
      "step": "string"
    }
    ```

## 4. Published Messages

The Remote Executor worker publishes status updates to the `conductor_queue`:

| Command               | Purpose                                                 |
| --------------------- | ------------------------------------------------------- |
| `execution_succeeded` | To signal that a remote command has completed successfully. |
| `execution_failed`    | To signal that a remote command has failed.             |

*   **Success Payload Schema:**
    ```json
    {
      "case_id": "string",
      "stdout": "string"
    }
    ```
*   **Failure Payload Schema:**
    ```json
    {
      "case_id": "string",
      "error_type": "RemoteExecutionError",
      "error_message": "string", // Contains stderr and exit code
      "original_payload": {}
    }
    ```

## 5. Key Features

*   **Command Failure Detection (Proposed Improvement):** The worker will be updated to treat any command that exits with a non-zero status code as a failure. This ensures that errors within the remote scripts are correctly caught and propagated to the `Conductor`.

## 6. Key Configuration Parameters

The worker's behavior is configured in the `ssh` section of the `config.yaml` file.

```yaml
ssh:
  host: "remote.hpc.com"
  port: 22
  username: "user"
  private_key_path: "/path/to/id_rsa"
```

## 7. Developer Guide

*   **Message Handling:** The main message handling logic is in `src/workers/remote_executor/handler.py`.
*   **SSH Logic:** The low-level SSH command execution logic is located in `src/workers/remote_executor/ssh_service.py`. This service uses the base `SSHManager` from `src/common/ssh_base.py` for connection handling.
