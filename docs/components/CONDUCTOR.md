# Component Guide: Conductor

## 1. Overview

The Conductor is the central orchestrator or "brain" of the MQI Communicator system. It is responsible for managing the lifecycle of each QA case, from the moment it is detected until it is either completed or has failed.

It does not perform any of the actual "work" (like file transfers or command execution) itself. Instead, it directs the various worker services by sending them commands via the message queue. It functions as a state machine, driven by messages from the workers.

## 2. Core Responsibilities

*   **Workflow Management:** Starts a new workflow when a `new_case_found` message is received.
*   **State Tracking:** Tracks the `status` and `workflow_step` of each case in the central database.
*   **Step Advancement:** Advances a case from one step to the next upon successful completion of the current step.
*   **Command Dispatching:** Publishes commands (e.g., `execute_command`, `upload_case`) to the appropriate worker queues to execute each workflow step.
*   **Resource Management:** Reserves and releases shared resources, such as GPUs, required for processing steps.
*   **Failure Handling:** Listens for failure events from workers and updates the case status to `FAILED`, ensuring the workflow is terminated correctly.

## 3. Consumed Messages

The Conductor listens to the `conductor_queue` for the following commands/events:

| Command                   | Source Worker         | Purpose                                               |
| ------------------------- | --------------------- | ----------------------------------------------------- |
| `new_case_found`          | Case Scanner          | To start a new workflow for a newly discovered case.  |
| `execution_succeeded`     | Remote Executor       | To signal that a remote command has completed successfully. |
| `execution_failed`        | Remote Executor       | To signal that a remote command has failed.           |
| `case_upload_completed`   | File Transfer         | To signal that case files have been uploaded.         |
| `results_download_completed` | File Transfer      | To signal that result files have been downloaded.     |
| `file_transfer_failed`    | File Transfer         | To signal that a file transfer operation has failed.  |

## 4. Published Messages

The Conductor publishes commands to the worker queues:

| Command           | Target Queue              | Purpose                                       |
| ----------------- | ------------------------- | --------------------------------------------- |
| `execute_command` | `remote_executor_queue`   | To execute a shell command on the remote HPC. |
| `upload_case`     | `file_transfer_queue`     | To upload a case directory to the remote HPC. |
| `download_results`| `file_transfer_queue`     | To download results from the remote HPC.      |

## 5. Workflow Logic (`advance_workflow`)

The core logic resides in the `WorkflowManager`'s `advance_workflow` method. The process is as follows:

1.  **Get Current State:** Fetches the case's current `workflow_step` from the database.
2.  **Determine Next Step:** Identifies the next step from the workflow definition in the configuration file.
3.  **Handle Completion:** If there is no next step, the workflow is marked as `COMPLETED`, and any reserved resources are released.
4.  **Reserve Resources:** If there is a next step, it attempts to reserve a GPU from the `gpu_resources` table.
    *   **If successful:** The case status is updated to `PROCESSING`.
    *   **If unsuccessful:** The case status is updated to `PENDING_RESOURCE`. The Conductor will attempt to advance this case again the next time a GPU is released by another completed or failed case.
5.  **Dispatch Command:** Based on the type of the next step (e.g., `execute`, `upload`), it formats and publishes the appropriate command message to the correct worker queue.

## 6. Key Configuration Parameters

The Conductor's behavior is configured in the `config.yaml` file.

```yaml
conductor:
  monitor_interval_sec: 60  # (This will be deprecated in favor of the orchestrator's trigger)
  remote_paths:
    upload_dir: /path/to/remote/upload
    download_dir: /path/to/remote/download

workflows:
  default_qa:
    - name: "upload_case_files"
      type: "upload"
      progress: 10
    - name: "run_interpreter"
      type: "execute"
      progress: 30
    - name: "run_moqui_sim"
      type: "execute"
      progress: 70
    - name: "download_results"
      type: "download"
      progress: 90

remote_commands:
  run_interpreter: "python /path/to/interpreter.py --case {case_id} --gpu {gpu_id}"
  run_moqui_sim: "python /path/to/moquisim.py --case {case_id} --gpu {gpu_id}"
```

## 7. Developer Guide

*   **Business Logic:** All core workflow and state transition logic is located in `src/conductor/workflow_manager.py`.
*   **Database Interactions:** All direct database queries are encapsulated in `src/conductor/state_service.py`. To add a new query, add a new method to the `StateService`.
*   **Adding a new workflow step:**
    1.  Add the step to the `workflows.default_qa` list in the config file, specifying its `name`, `type`, and `progress`.
    2.  If it's an `execute` step, add a corresponding command template to the `remote_commands` section.
    3.  Ensure the `Conductor`'s `_dispatch_workflow_step` logic can handle the new step `type`.
