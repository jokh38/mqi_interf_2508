# 1. Architecture Overview

This document provides a high-level overview of the MQI Communicator system's architecture, its core design principles, and the technology stack used.

## 1.1. Core Architectural Pattern

The system is designed using a **Microservices Architecture**. It is composed of several small, independent, and loosely-coupled services that work together to perform the overall QA workflow. This pattern was chosen to enhance modularity, scalability, and maintainability.

Each service has a single, well-defined responsibility and can be developed, deployed, and scaled independently.

## 1.2. Design Principles

The architecture is built upon the following key design principles:

*   **Asynchronous & Event-Driven:** Communication between services is primarily asynchronous and event-driven, orchestrated via a central message broker (RabbitMQ). This decouples the services and makes the system resilient to temporary failures of individual components. Services react to incoming messages (events or commands) rather than making direct, blocking calls to each other.

*   **Centralized State, Decentralized Logic:** While the business logic is decentralized across various worker services, the system's state is centralized in a single SQLite database. The `Conductor` service acts as the master of this state, ensuring that the workflow progresses correctly, but each worker is responsible for its own piece of the logic.

*   **Robustness and Resilience:** The system is designed to be resilient to failure. Key patterns include:
    *   **Persistent Messaging:** Important messages are persisted to disk by the message broker to survive restarts.
    *   **Dead Letter Queues (DLQs):** Messages that repeatedly fail processing are automatically routed to a DLQ for later inspection, preventing them from blocking the system.
    *   **Automatic Retries:** Key operations, such as connecting to services or processing messages, employ an exponential backoff retry strategy to handle transient failures gracefully.
    *   **Health Monitoring:** A central orchestrator monitors the health of all services and can restart them if they fail.

*   **Configuration-Driven:** The behavior of the system and its components is heavily driven by a central YAML configuration file. This includes workflow definitions, service enablement, connection parameters, and command templates. This allows for significant flexibility without requiring code changes.

## 1.3. System Components

The system consists of the following high-level components:

*   **Main Orchestrator:** The entry point of the system. It is responsible for starting, stopping, and monitoring all other services.

*   **Conductor:** The "brain" of the system. It listens for events, manages the state of each QA case as it moves through the workflow, and dispatches commands to the appropriate workers.

*   **Workers:** A pool of specialized services that perform the actual tasks. Each worker typically listens to a specific queue for commands:
    *   `Case Scanner`: Polls the filesystem for new input cases.
    *   `File Transfer`: Handles uploading and downloading files via SFTP.
    *   `Remote Executor`: Executes shell commands on a remote HPC system via SSH.
    *   `System Curator`: Periodically monitors the state of external resources (like GPUs).
    *   `Archiver`: Performs periodic database maintenance and backups.

*   **Dashboard:** A web-based interface (built with FastAPI) that provides a real-time view of the system's status, active jobs, and resource utilization.

## 1.4. Technology Stack

*   **Language:** Python 3
*   **Web Framework:** FastAPI (for the Dashboard) with Uvicorn
*   **Messaging:** RabbitMQ (via the `pika` library)
*   **Database:** SQLite
*   **Remote Operations:** Paramiko (for SSH/SFTP)
*   **Configuration:** PyYAML
*   **Testing:** Pytest, pytest-mock, pytest-cov
