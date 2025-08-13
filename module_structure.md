# Module Structure and Dependencies

This document outlines the entry points and dependencies of the major components in the MQI system.

## Core Components

### Orchestrator
- **Entry Point**: `src/main_orchestrator.py`
- **Dependencies**:
  - `ProcessManager`
  - `HealthMonitor`
  - `MessageBroker`
  - `DatabaseManager`
  - `load_config`
  - `get_logger`

### Process Manager
- **Entry Point**: `src/process_manager.py` (Class used by Orchestrator)
- **Dependencies**:
  - `paramiko` (for remote processes)
  - `psutil` (for local processes)

## PROCESS_MODULES Contract

This table defines the mapping between process names and their corresponding module paths, as defined in `src/process_manager.py`.

| Process Name      | Module Path                         |
|-------------------|-------------------------------------|
| `conductor`       | `src.conductor.main`                |
| `case_scanner`    | `src.workers.case_scanner.main`     |
| `file_transfer`   | `src.workers.file_transfer.main`    |
| `remote_executor` | `src.workers.remote_executor.main`  |
| `system_curator`  | `src.workers.system_curator.main`   |
| `archiver`        | `src.workers.archiver.main`         |
| `dashboard`       | `src.dashboard.main`                |

## Service Components

### Conductor
- **Entry Point**: `src/conductor/main.py`
- **Dependencies**:
  - `load_config`
  - `DatabaseManager`
  - `MessageQueue`
  - `WorkflowManager`

### Dashboard
- **Entry Point**: `src/dashboard/main.py`
- **Dependencies**:
  - `uvicorn`
  - `load_config`
  - `DatabaseManager`
  - `get_logger`
  - `DashboardService`
    - **Note**: The `DashboardService` (from `src/dashboard/dashboard_service.py`, not `dashboard_seryamlvice`) depends on `FastAPI` and `DataCollector`.

## Worker Components

All workers share a similar structure, with a `main.py` entry point that initializes a handler.

| Worker            | Entry Point                               | Handler Class             | Key Dependencies                                      |
|-------------------|-------------------------------------------|---------------------------|-------------------------------------------------------|
| **case_scanner**  | `src/workers/case_scanner/main.py`        | `CaseScannerHandler`      | `load_config`, `MessageQueue`, `DatabaseManager`      |
| **file_transfer** | `src/workers/file_transfer/main.py`       | `FileTransferHandler`     | `load_config`, `MessageQueue`, `DatabaseManager`      |
| **remote_executor**| `src/workers/remote_executor/main.py`     | `RemoteExecutorHandler`   | `load_config`, `MessageQueue`, `DatabaseManager`      |
| **system_curator**| `src/workers/system_curator/main.py`      | `SystemCuratorHandler`    | `load_config`, `MessageQueue`, `DatabaseManager`      |
| **archiver**      | `src/workers/archiver/main.py`            | `ArchiverHandler`         | `load_config`, `MessageQueue`, `DatabaseManager`      |
