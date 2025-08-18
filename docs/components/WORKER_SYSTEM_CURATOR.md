# Component Guide: System Curator Worker

## 1. Overview

The System Curator worker is a specialized service responsible for monitoring the state of external resources, specifically the GPUs on the remote HPC system.

It is a message-driven worker that is triggered periodically. Its purpose is to keep the central database's view of GPU resources synchronized with their actual, real-time status.

## 2. Core Responsibilities

*   **Fetch GPU Metrics:** When triggered, it connects to the remote HPC via SSH and runs a command (e.g., `nvidia-smi`) to fetch detailed metrics for all available GPUs.
*   **Update Database:** It takes the collected metrics and "upserts" them into the `gpu_resources` table in the central database. This means it updates existing GPU records and creates new ones if new GPUs are detected.

## 3. Consumed Messages

The System Curator worker listens to the `system_curator_queue` for one command:

| Command          | Source              | Purpose                                    |
| ---------------- | ------------------- | ------------------------------------------ |
| `system_monitor` | Main Orchestrator   | To trigger a resource monitoring cycle.    |

*   **Payload Schema:**
    ```json
    {
      "triggered_by": "orchestrator",
      "timestamp": "float"
    }
    ```

## 4. Published Messages

The System Curator **does not publish any messages**. Its job is only to update the shared database state for other services (like the Conductor) to use.

## 5. Key Features

*   **Decoupled Monitoring:** The monitoring logic is decoupled from the main workflow. The `Conductor` does not need to know how to check GPU status; it simply reads the state from the `gpu_resources` table, which the System Curator keeps up-to-date.
*   **Dynamic Resource Discovery:** The worker can automatically discover and register new GPUs that are added to the remote HPC system.

## 6. Key Configuration Parameters

The worker's behavior is configured in the `curator` and `ssh` sections of the `config.yaml` file.

```yaml
# Used by the orchestrator to time the trigger
curator:
  monitor_interval_sec: 60
  gpu_monitor_command: "nvidia-smi --query-gpu=index,uuid,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits"

ssh:
  host: "remote.hpc.com"
  port: 22
  username: "user"
  private_key_path: "/path/to/id_rsa"
```

## 7. Developer Guide

*   **Message Handling:** The main message handling logic is in `src/workers/system_curator/handler.py`.
*   **Metric Fetching:** The logic for connecting to the remote HPC and parsing the command output is in `src/workers/system_curator/monitor_service.py`.
*   **Database Updates:** The logic for updating the `gpu_resources` table is in `src/workers/system_curator/db_service.py`.
