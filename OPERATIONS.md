# MQI Communicator System Operations Guide

## Overview

This document provides operational procedures for the MQI Communicator System, including startup, shutdown, monitoring, and troubleshooting.

## Table of Contents

1. [System Startup and Shutdown](#system-startup-and-shutdown)
2. [Monitoring and Health Checks](#monitoring-and-health-checks)
3. [Maintenance Procedures](#maintenance-procedures)
4. [Backup and Recovery](#backup-and-recovery)
5. [Troubleshooting](#troubleshooting)
6. [Log Management](#log-management)

## System Startup and Shutdown

### Normal Startup Sequence

1. **Check Prerequisites**
   - Verify RabbitMQ is running.
   - Check database accessibility.
   - Verify network connectivity to HPC systems.

2. **Start System**
   - It is recommended to use the `run.bat` script to start the system.
   - Alternatively, you can run the main orchestrator directly:
   ```bash
   python -m src.main_orchestrator config/config.development.yaml
   ```

3. **Verify Startup**
   - Check the logs for any errors.
   - Use the dashboard to monitor the system status.

### Graceful Shutdown Sequence

1. **Prepare for Shutdown**
   - Check for active cases in the dashboard or by querying the database:
   ```sql
   SELECT COUNT(*) FROM cases WHERE status IN ('PROCESSING', 'EXECUTING');
   ```

2. **Stop System**
   - Press `Ctrl+C` in the terminal where the main orchestrator is running.

3. **Verify Shutdown**
   - Ensure that all processes related to the application have been terminated.

## Monitoring and Health Checks

### System Health Dashboard
The primary tool for monitoring the system is the web dashboard. It provides real-time information about the status of the components, active cases, and resource utilization.

#### Key Metrics to Monitor
- **System Resources**: CPU, memory, and disk usage of the server running the application.
- **Application Health**: Status of each component (conductor, workers) in the dashboard.
- **Database Health**: Check for database connection errors in the logs.
- **Message Queue Health**: Monitor the number of messages in the queues using the RabbitMQ management UI.
- **Business Metrics**:
  - Active cases and their status.
  - GPU utilization.
  - Processing throughput.

## Maintenance Procedures

### Daily Maintenance
- **Log Review**: Check the application logs for any errors or warnings.
- **System Health Check**: Use the dashboard to check the health of the system.
- **Database Maintenance**: Check for stuck cases that have been in a processing state for an unusually long time.

### Weekly Maintenance
- **Performance Review**: Analyze the processing statistics from the database to identify any performance bottlenecks.
- **Log Rotation and Cleanup**: Manually archive or delete old log files.
- **Security Updates**: Keep the system and its dependencies up to date.

## Backup and Recovery

### Database Backup
- **Manual Backup**:
  ```bash
  sqlite3 data/mqi_system_dev.db ".backup 'data/backup.db'"
  ```
- **Backup Restoration**:
  1. Stop the system.
  2. Replace the database file with the backup.
  3. Restart the system.

### Configuration Backup
- Manually create a copy of the `config` directory.

## Troubleshooting

### Common Issues and Solutions

#### System Won't Start
- **Symptoms**: The main orchestrator process exits immediately after starting.
- **Diagnosis**: Check the logs for configuration errors, database connection issues, or problems with RabbitMQ.
- **Solutions**:
  - Correct any errors in the configuration file.
  - Ensure that the database file is accessible and not corrupted.
  - Make sure that RabbitMQ is running and accessible.

#### High Memory Usage
- **Symptoms**: The system becomes unresponsive or crashes.
- **Diagnosis**: Use system monitoring tools to identify the process that is consuming a large amount of memory.
- **Solutions**:
  - Restart the system.
  - Investigate the cause of the memory leak.

#### Database Corruption
- **Symptoms**: The application logs show database errors.
- **Diagnosis**: Use the `PRAGMA integrity_check;` command in `sqlite3` to check the integrity of the database.
- **Solutions**:
  - Stop the system and restore the database from a backup.

#### Network Connectivity Issues
- **Symptoms**: The application is unable to connect to the HPC system or RabbitMQ.
- **Diagnosis**: Use tools like `ping` and `telnet` to check the network connectivity.
- **Solutions**:
  - Verify the network configuration and firewall rules.
  - Ensure that the HPC system and RabbitMQ are running and accessible.

## Log Management

### Log File Locations
- **Application Logs**: Check the `logs` directory.

### Log Analysis
- Use standard command-line tools like `grep` and `tail` to analyze the log files.
- The logs contain information about the operations of each component, which can be useful for debugging and monitoring.
