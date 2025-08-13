# MQI Interface System - Code Structure Analysis

## System Overview
The MQI (Moqui) Interface system is a distributed microservice architecture designed for automated file processing and remote command execution. It uses a message-queue based architecture with RabbitMQ for inter-service communication.

## Architecture Pattern
- **Microservice Architecture**: Independent worker services communicating via message queues
- **Event-driven**: Asynchronous message passing between services
- **Process-based**: Each service runs as a separate process managed by ProcessManager
- **Database-centric**: SQLite database for state management and coordination

## 1. File Structure

The project is organized into the following main directories:

-   `src/`: Contains the core source code for the application.
    -   `common/`: Shared utilities for configuration, database access, messaging, and logging.
    -   `conductor/`: The central workflow orchestrator.
    -   `dashboard/`: The dashboard service.
    -   `workers/`: Individual worker modules for specific tasks (e.g., `case_scanner`, `file_transfer`).
-   `tests/`: Contains unit and integration tests for the modules.
    -   `integration/`: Contains integration tests.
-   `config/`: Holds configuration files for different environments (e.g., `config.development.yaml`).
-   `scripts/`: Includes setup and utility scripts for database initialization, message queue setup, etc.
-   `data/`: Stores data files, including the SQLite database.
-   `docs/`: For documentation files.

## 2. Core Components Hierarchy

### Main Orchestrator (`src/main_orchestrator.py`)
**Purpose**: System-wide coordinator and entry point
**Dependencies**:
- `src.common.config_loader` → Configuration management
- `src.common.db_utils.DatabaseManager` → Database operations
- `src.common.logger` → Logging system  
- `src.process_manager.ProcessManager` → Process lifecycle management
- `src.health_monitor.HealthMonitor` → System health monitoring

**Key Responsibilities**:
- Initialize all system components
- Start/stop worker processes
- Handle graceful shutdown signals
- Monitor overall system health

### Process Manager (`src/process_manager.py`)
**Purpose**: Manage worker process lifecycle
**Dependencies**:
- `src.common.exceptions` → Error handling
- Standard library: `subprocess`, `threading`, `time`

**Managed Processes**:
```python
PROCESS_MODULES = {
    'conductor': 'src.conductor.main',
    'dashboard': 'src.dashboard.main',
    'case_scanner': 'src.workers.case_scanner.main', 
    'file_transfer': 'src.workers.file_transfer.main',
    'remote_executor': 'src.workers.remote_executor.main',
    'system_curator': 'src.workers.system_curator.main',
    'archiver': 'src.workers.archiver.main'
}
```

### Conductor (`src/conductor/main.py`)
**Purpose**: Workflow orchestration and state management
**Dependencies**:
- `src.common.config_loader` → Configuration loading
- `src.common.db_utils.DatabaseManager` → Database operations
- `src.common.messaging.MessageQueue` → Message queue operations
- `src.common.exceptions` → Error handling
- `src.conductor.workflow_manager.WorkflowManager` → Workflow logic

### Dashboard (`src/dashboard/main.py`)
**Purpose**: Provides a web-based dashboard for monitoring the system.
**Dependencies**:
- `src.common.config_loader`
- `src.common.db_utils.DatabaseManager`
- `src.dashboard.dashboard_seryamlvice`
- `src.dashboard.data_collector`

## 3. Worker Services Architecture

### Case Scanner (`src/workers/case_scanner/`)
**Structure**:
- `main.py` → Entry point and configuration loading
- `handler.py` → Message handling and scanning logic  
- `scanner_service.py` → Directory scanning implementation

### File Transfer (`src/workers/file_transfer/`)
**Structure**:
- `main.py` → Entry point and initialization
- `handler.py` → Message handling for file operations
- `sftp_service.py` → SFTP implementation for file transfers
- `utils.py` → File transfer utilities

### Remote Executor (`src/workers/remote_executor/`)
**Structure**:
- `main.py` → Entry point
- `handler.py` → Message handling for command execution
- `ssh_service.py` → SSH command execution service

### System Curator (`src/workers/system_curator/`)
**Structure**:
- `main.py` → Entry point
- `handler.py` → Message handling for system curation
- `db_service.py` → Database management operations
- `monitor_service.py` → System monitoring and cleanup

### Archiver (`src/workers/archiver/`)
**Structure**:
- `main.py` → Entry point  
- `handler.py` → Message handling for archiving
- `archiver_service.py` → File archival and cleanup operations

## 4. Common Utilities (`src/common/`)

- **`config_loader.py`**: YAML configuration parsing and validation
- **`db_utils.py`**: Thread-safe SQLite database operations
- **`logger.py`**: Centralized logging with database storage
- **`messaging.py`**: RabbitMQ wrapper for message queue operations
- **`exceptions.py`**: Custom exception classes
- **`ssh_base.py`**: Base SSH functionality for remote operations

## 5. Testing (`tests/`)
- **`test_archiver.py`**: Unit tests for the Archiver worker.
- **`test_case_scanner.py`**: Unit tests for the Case Scanner worker.
- **`test_conductor.py`**: Unit tests for the Conductor.
- **`test_data_collector.py`**: Unit tests for the Dashboard data collector.
- **`test_file_transfer.py`**: Unit tests for the File Transfer worker.
- **`test_health_monitor.py`**: Unit tests for the Health Monitor.
- **`test_main_orchestrator.py`**: Unit tests for the Main Orchestrator.
- **`test_process_manager.py`**: Unit tests for the Process Manager.
- **`test_remote_executor.py`**: Unit tests for the Remote Executor worker.
- **`test_system_curator.py`**: Unit tests for the System Curator worker.
- **`integration/`**: Integration tests for the system.
    - **`test_complete_workflow.py`**: Tests a complete workflow from start to finish.
    - **`test_complete_workflow_simple.py`**: A simpler version of the complete workflow test.
    - **`test_concurrent_processing.py`**: Tests the system's ability to handle concurrent processing.
    - **`test_failure_recovery.py`**: Tests the system's failure recovery mechanisms.
    - **`test_performance.py`**: Tests the performance of the system.
    - **`test_system_coordination.py`**: Tests the coordination between different system components.

## 6. External Dependencies

### Runtime Requirements (`pyproject.toml`):
```
pika==1.3.1
paramiko==3.4.0
PyYAML==6.0.1
APScheduler==3.10.1
psutil==5.9.5
cryptography==43.0.1
structlog==23.1.0
fastapi==0.104.1
uvicorn==0.24.0
jinja2==3.1.2
```

### Development/Testing (`pyproject.toml`):
```
pytest==7.4.0
pytest-asyncio==0.21.0
pytest-cov==4.1.0
black==23.3.0
ruff==0.1.9
mypy==1.4.1
```

## 7. Usage and Execution

### Starting the Entire System

```bash
python3 -m src.main_orchestrator config/config.development.yaml
```

### Running Standalone Workers

```bash
# File Transfer
python3 run_file_transfer.py

# Remote Executor
python3 run_remote_executor.py
```
