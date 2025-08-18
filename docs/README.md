# MQI Communicator - System Design Document

## 1. Introduction

Welcome to the System Design Document (SDD) for the MQI Communicator system. This document provides a comprehensive architectural and technical overview of the system. It is intended for developers who will be building, maintaining, and extending the system.

The MQI Communicator is a distributed, microservice-based application designed to automate the medical physics Quality Assurance (QA) workflow. It detects new cases, transfers files, executes remote calculations, and manages the entire process in a robust and scalable manner.

This documentation describes the **ideal architecture** and **standardized practices** for the project. All future development should adhere to the principles outlined herein.

## 2. Table of Contents

This documentation is organized into several key sections.

*   **Core Concepts:**
    *   [**1. Architecture Overview**](./01_ARCHITECTURE.md) - A high-level view of the microservices architecture, design principles, and technology stack.
    *   [**2. Setup and Execution**](./02_SETUP_AND_RUN.md) - Instructions for setting up the development environment and running the system.

*   **System Contracts & Schemas:**
    *   [**3. Database Schema**](./03_DATABASE_SCHEMA.md) - Detailed descriptions of all database tables, columns, and their purposes.
    *   [**4. Communication Protocol**](./04_COMMUNICATION_PROTOCOL.md) - A complete guide to the RabbitMQ message queues, message types, and payload schemas.

*   **Development Standards:**
    *   [**5. Development Standards**](./05_DEVELOPMENT_STANDARDS.md) - A comprehensive guide covering:
        *   Coding Style and Conventions
        *   Test-Driven Development (TDD) Strategy
        *   Unified Logging and Error Handling Strategy

*   **Component Guides:**
    *   [**Conductor**](./components/CONDUCTOR.md) - The central workflow orchestrator.
    *   [**Case Scanner Worker**](./components/WORKER_CASE_SCANNER.md) - The worker responsible for detecting new cases.
    *   [**File Transfer Worker**](./components/WORKER_FILE_TRANSFER.md) - The worker responsible for SFTP file operations.
    *   [**Remote Executor Worker**](./components/WORKER_REMOTE_EXECUTOR.md) - The worker responsible for executing remote commands.
    *   [**System Curator Worker**](./components/WORKER_SYSTEM_CURATOR.md) - The worker responsible for monitoring system resources.
    *   [**Archiver Worker**](./components/WORKER_ARCHIVER.md) - The worker responsible for database maintenance and backups.
    *   [**Dashboard**](./components/DASHBOARD.md) - The web-based monitoring interface.
