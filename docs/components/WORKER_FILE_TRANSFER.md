# Component Guide: File Transfer Worker

## 1. Overview

The File Transfer worker is responsible for all file transfer operations between the local system and the remote HPC (High-Performance Computing) cluster. It uses the SFTP protocol for secure and reliable transfers.

This worker is purely message-driven; it listens for commands on a dedicated queue and performs the requested transfer.

## 2. Core Responsibilities

*   **Upload Files/Directories:** Handles the upload of entire case directories from the local machine to the remote HPC.
*   **Download Files/Directories:** Handles the download of result directories from the remote HPC back to the local machine.
*   **Data Integrity Verification:** After every transfer (both upload and download), it calculates the checksum of the source and destination files/directories to ensure the transfer was successful and the data is not corrupt.
*   **Status Reporting:** It reports the success or failure of each transfer operation back to the `Conductor`.

## 3. Consumed Messages

The File Transfer worker listens to the `file_transfer_queue` for the following commands:

| Command            | Source    | Purpose                                        |
| ------------------ | --------- | ---------------------------------------------- |
| `upload_case`      | Conductor | To upload a case directory to the remote HPC.  |
| `download_results` | Conductor | To download a results directory from the remote HPC. |

*   **Payload Schema (for both commands):**
    ```json
    {
      "case_id": "string",
      "local_path": "string",
      "remote_path": "string"
    }
    ```

## 4. Published Messages

The File Transfer worker publishes status updates to the `conductor_queue`:

| Command                      | Purpose                                       |
| ---------------------------- | --------------------------------------------- |
| `case_upload_completed`      | To signal that a case upload has finished successfully. |
| `results_download_completed` | To signal that a results download has finished successfully. |
| `file_transfer_failed`       | To signal that a file transfer operation has failed after all retries. |

*   **Success Payload Schema:**
    ```json
    {
      "case_id": "string",
      "local_path": "string",
      "remote_path": "string"
    }
    ```
*   **Failure Payload Schema:**
    ```json
    {
      "case_id": "string",
      "error_type": "DataIntegrityError | NetworkError | ...",
      "error_message": "string",
      "original_payload": {}
    }
    ```

## 5. Key Features

*   **Retry with Exponential Backoff:** If a transfer fails due to a transient network error, the worker will automatically retry the operation several times with an increasing delay.
*   **Checksum Verification:** The worker does not assume a transfer was successful. It calculates a SHA256 checksum of the entire directory structure on both the source and destination and compares them. The transfer is only considered successful if the checksums match.

## 6. Key Configuration Parameters

The worker's behavior is configured in the `sftp` section of the `config.yaml` file.

```yaml
sftp:
  host: "remote.hpc.com"
  port: 22
  username: "user"
  private_key_path: "/path/to/id_rsa"
```

## 7. Developer Guide

*   **Message Handling:** The main message handling logic is in `src/workers/file_transfer/handler.py`.
*   **SFTP Logic:** All low-level SFTP operations (connection, transfer, verification) are encapsulated in `src/workers/file_transfer/sftp_service.py`.
*   **Checksum Logic:** The checksum calculation functions are located in `src/workers/file_transfer/utils.py`.
