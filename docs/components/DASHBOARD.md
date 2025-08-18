# Component Guide: Dashboard

## 1. Overview

The Dashboard is a web-based interface that provides a real-time, at-a-glance view of the MQI Communicator system's status and activity.

It is a standalone service powered by the FastAPI web framework.

## 2. Core Responsibilities

*   **Display System Status:** Shows the overall health of the system (e.g., `healthy`, `warning`, `error`).
*   **Monitor Active Jobs:** Lists all QA cases that are currently being processed, along with their status, current workflow step, and progress.
*   **Visualize Resource Usage:** Displays real-time metrics for GPU resources, including utilization, memory usage, and temperature.
*   **Track Worker Health:** Shows the status (`running` or `stopped`) of each individual microservice process.
*   **Show Recent Activity:** Provides a log of the most recent events in the system, such as case completions and failures.

## 3. Architecture

The Dashboard service has two main parts:

*   **Backend (`dashboard_service.py`):** A FastAPI application that serves the frontend and provides a set of RESTful API endpoints and a Server-Sent Events (SSE) stream.
*   **Frontend (`index.html`, `dashboard.js`, `dashboard.css`):** A single-page web application that connects to the backend's SSE stream and dynamically updates the UI with the real-time data it receives.

### Real-time Updates via Server-Sent Events (SSE)

The frontend does not constantly poll the backend for updates. Instead, it maintains a single, persistent connection to the `/events` endpoint. The backend uses this connection to push a complete snapshot of the system's state to the frontend every few seconds. This is an efficient mechanism for providing real-time updates.

## 4. Data Collection

The backend does not contain any business logic itself. It delegates all data gathering to the `DataCollector` class (`data_collector.py`). The `DataCollector` is responsible for querying the central database and interacting with other system components (like the `ProcessManager`) to aggregate all the information needed by the frontend.

## 5. Key Configuration Parameters

The Dashboard's behavior is configured in the `dashboard` section of the `config.yaml` file.

```yaml
dashboard:
  host: "0.0.0.0"
  port: 8080
  refresh_interval_sec: 5
```

## 6. Developer Guide

*   **Backend Entry Point:** The web server is started via `src/dashboard/main.py`.
*   **API and SSE Logic:** The FastAPI application, including all API routes and the SSE stream logic, is defined in `src/dashboard/dashboard_service.py`.
*   **Data Aggregation:** All logic for fetching and aggregating data from other parts of the system is located in `src/dashboard/data_collector.py`.
*   **Frontend Files:** The frontend user interface is defined by the files in `src/dashboard/templates/` (HTML) and `src/dashboard/static/` (CSS and JavaScript).
