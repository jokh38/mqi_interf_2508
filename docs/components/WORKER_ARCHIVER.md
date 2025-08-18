# Component Guide: Archiver Worker

## 1. Overview

The Archiver worker is a maintenance service responsible for managing the size of the production database and creating backups.

It is a message-driven worker that is triggered periodically to perform its tasks.

## 2. Core Responsibilities

*   **Archive Old Data:** It identifies `COMPLETED` and `FAILED` cases that are older than a configured retention period and moves them from the "live" `cases` and `case_history` tables to the `archived_cases` and `archived_case_history` tables. This keeps the production tables smaller and more performant.
*   **Database Backup:** It creates a timestamped backup of the entire SQLite database file.

## 3. Consumed Messages

The Archiver worker listens to the `archiver_queue` for one command:

| Command        | Source                            | Purpose                                  |
| -------------- | --------------------------------- | ---------------------------------------- |
| `archive_data` | (External Scheduler or future component) | To trigger a database maintenance cycle. |

*   **Payload Schema:** `{}` (Empty)

## 4. Published Messages

The Archiver **does not publish any messages**. Its work is self-contained within the database.

## 5. Key Features

*   **Transactional Archival:** The entire archival process (copying to archive tables, deleting from live tables) is performed within a single database transaction to ensure data integrity.
*   **Filesystem Backup:** It uses the standard `sqlite3` command-line tool's `.backup` command to create a reliable hot backup of the database file.

## 6. Key Configuration Parameters

The worker's behavior is configured in the `archiver` section of the `config.yaml` file.

```yaml
archiver:
  retention_days: 180
  backup_path: "/path/to/db_backups"
```

## 7. Developer Guide

*   **Message Handling:** The main message handling logic is in `src/workers/archiver/handler.py`.
*   **Archival and Backup Logic:** The low-level database operations for archiving and the subprocess call for backing up the database are located in `src/workers/archiver/archiver_service.py`.
*   **Important Note (Proposed Fix):** The `archived_cases` and `archived_case_history` tables are not automatically created. A proposed improvement is to add the `CREATE TABLE` statements for these tables to the main database initialization logic in `src/common/db_utils.py`.
*   **Security Note (Proposed Fix):** The SQL queries for archiving use f-strings, which presents a potential SQL injection risk. A proposed improvement is to refactor these queries to use parameterized statements.
