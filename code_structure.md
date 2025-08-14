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

### Conductor (`src/conductor/`)
**Structure**:
- `main.py` → Entry point and configuration loading
- `state_service.py` → Manages the state of the system.
- `workflow_manager.py` → Workflow logic

### Dashboard (`src/dashboard/`)
**Structure**:
- `main.py` → Entry point
- `dashboard_service.py` → The main service for the dashboard.
- `data_collector.py` → Collects data for the dashboard.
- `static/` → Static files (CSS, JS, images).
- `templates/` → HTML templates for the dashboard.


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
- `remote_executor.py` → Remote command execution utilities.

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
- **`ssh_client_manager.py`**: Manages SSH clients.

## 5. Testing (`tests/`)

The `tests/` directory is intended to contain unit and integration tests for the various modules in the system. However, the test files are not yet implemented.

## 6. External Dependencies

### Runtime Requirements (`requirements.txt`):
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

The easiest way to start the entire system is to use the `run.bat` script, which starts the main orchestrator with the default configuration file.

```bash
run.bat
```

Alternatively, you can run the main orchestrator directly:

```bash
python3 -m src.main_orchestrator config/config.development.yaml
```

### Running Standalone Workers

You can also run individual workers for testing or development purposes.

```bash
# File Transfer
python3 run_file_transfer.py

# Remote Executor
python3 run_remote_executor.py
```