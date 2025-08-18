# 2. Setup and Execution Guide

This guide provides instructions for setting up the development environment, installing dependencies, and running the MQI Communicator system.

## 2.1. Prerequisites

Before you begin, ensure you have the following installed on your system:

*   **Python 3.8+**
*   **RabbitMQ:** A running instance of RabbitMQ is required for messaging. You can run it locally via Docker or install it directly.
*   **SSH/SFTP Server:** For testing features like `File Transfer` and `Remote Executor`, you will need access to an SSH/SFTP server.

## 2.2. Environment Setup

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd mqi-communicator
    ```

2.  **Create a Virtual Environment:**
    It is highly recommended to use a Python virtual environment to manage dependencies.
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install Dependencies:**
    Install all required Python packages using the `requirements.txt` file.
    ```bash
    pip install -r requirements.txt
    ```
    For development and running tests, also install the development dependencies from `pyproject.toml`.
    ```bash
    pip install "pytest" "pytest-mock" "pytest-cov" "black" "ruff" "mypy"
    ```

## 2.3. Configuration

The system's behavior is controlled by a central YAML configuration file.

1.  **Copy the Default Config:**
    Start by copying the default configuration file to create a development-specific version.
    ```bash
    cp config/config.default.yaml config/config.development.yaml
    ```

2.  **Update `config.development.yaml`:**
    Open `config/config.development.yaml` and update the following sections with your local environment details:
    *   **`rabbitmq.url`**: The AMQP URL for your RabbitMQ instance (e.g., `amqp://guest:guest@localhost:5672/`).
    *   **`database.path`**: The local path for the SQLite database file (e.g., `data/mqi_system_dev.db`).
    *   **`scanner.target_directory`**: A local directory path that the `CaseScanner` will monitor for new cases.
    *   **`sftp` and `ssh`**: Connection details for your test SSH/SFTP server.

## 2.4. Running the System

### Running the Entire System

The `MainOrchestrator` is the primary entry point for running the entire system. It will start all the services marked as `enabled: true` in your configuration file.

To run the system, execute the following command from the project root:
```bash
python -m src.main_orchestrator config/config.development.yaml
```

You should see log output indicating that the orchestrator and its managed processes are starting up.

### Running Individual Services

For development and debugging, you can run each microservice independently. This allows you to focus on a single component.

First, ensure the `MQI_CONFIG_PATH` environment variable is set (optional, but good practice):
```bash
export MQI_CONFIG_PATH=config/config.development.yaml
# On Windows: set MQI_CONFIG_PATH=config\config.development.yaml
```

Then, run the desired service using its `main` module:

*   **Conductor:**
    ```bash
    python -m src.conductor.main
    ```
*   **Case Scanner:**
    ```bash
    python -m src.workers.case_scanner.main
    ```
*   **File Transfer:**
    ```bash
    python -m src.workers.file_transfer.main
    ```
*   **Remote Executor:**
    ```bash
    python -m src.workers.remote_executor.main
    ```
*   **System Curator:**
    ```bash
    python -m src.workers.system_curator.main
    ```
*   **Archiver:**
    ```bash
    python -m src.workers.archiver.main
    ```
*   **Dashboard:**
    ```bash
    python -m src.dashboard.main
    ```

When running services individually, they will still connect to the central RabbitMQ and database instances defined in your configuration, allowing them to interact with other running services.
