# Gateway Maintenance Script Documentation

## Overview

The `maintenance.ps1` script performs routine maintenance tasks for the NHS Rubie Gateway installation. It provides automated operations for:

* MWL database backup
* PACS database backup
* PACS storage archiving
* Service log rotation

The script ensures that Gateway services are safely stopped before maintenance activities are performed and restarted afterwards.

---

# Script Location

```text
<InstallPath>\current\scripts\powershell\maintenance.ps1
```

Default installation path:

```text
C:\Program Files\NHS\ManageBreastScreeningGateway
```

Scheduled tasks are configured in the Windows Task Scheduler via the `deploy.ps1` script.
The `deploy.ps1` script is located at:

```text
<InstallPath>\current\scripts\powershell\deploy.ps1
```

---

# Parameters

| Parameter         | Description                                             | Default                                             |
| ----------------- | ------------------------------------------------------- | --------------------------------------------------- |
| `BaseInstallPath` | Root installation directory of the Gateway application. | `C:\Program Files\NHS\ManageBreastScreeningGateway` |
| `Action`          | Maintenance operation to execute.                       | None                                                |

### Supported Actions

| Action               | Description                                                           |
| -------------------- | --------------------------------------------------------------------- |
| `BackupMWLDatabase`  | Creates a backup of the MWL database.                                 |
| `BackupPACSDatabase` | Creates a backup of the PACS database and archives stored PACS files. |
| `RotateLogs`         | Rotates Gateway service log files.                                    |

### Example

```powershell
.\maintenance.ps1 -Action BackupMWLDatabase
```

---

# Logging

Maintenance activity is recorded in:

```text
<InstallPath>\logs\maintenance.log
```

Each log entry includes:

* Timestamp
* Log level
* Message

Example:

```text
[2026-01-01 02:00:00.123] [INFO] Starting database backup...
```

### Log Levels

| Level   | Meaning                               |
| ------- | ------------------------------------- |
| INFO    | Informational messages                |
| SUCCESS | Successful completion of an operation |
| WARNING | Non-critical issue                    |
| ERROR   | Operation failure                     |

---

# Gateway Service Management

The script automatically discovers services matching:

```text
Gateway-*
```

Examples:

```text
Gateway-MWL
Gateway-PACS
Gateway-Relay
Gateway-Listener
```

## Service Stop Process

Before maintenance operations begin:

1. Each running Gateway service is stopped.
2. Service state is monitored until it reaches `Stopped`.
3. If a service fails to stop within the configured timeout, an exception is raised and processing stops.

## Service Start Process

After maintenance operations complete:

1. Each Gateway service is started.
2. Service state is monitored until it reaches `Running`.
3. Successful startup is logged.

---

# Database Backup Operations

## Common Backup Configuration

The script sets the following environment variables before invoking the Python backup utility:

| Variable      | Value                                  |
| ------------- | -------------------------------------- |
| `PYTHONPATH`  | `<InstallPath>\current\scripts\python` |
| `BACKUP_PATH` | `<InstallPath>\data\backups`           |
| `MAX_BACKUPS` | `5`                                    |

The backup process is executed using:

```powershell
..\python\database.py
```

Only the most recent five backups are retained.

---

## MWL Database Backup

Action:

```powershell
BackupMWLDatabase
```

Database configuration:

| Setting       | Value                            |
| ------------- | -------------------------------- |
| Database File | `<InstallPath>\data\worklist.db` |
| Table Name    | `worklist_items`                 |

Process:

1. Stop Gateway services.
2. Backup MWL database.
3. Restart Gateway services.

---

## PACS Database Backup

Action:

```powershell
BackupPACSDatabase
```

Database configuration:

| Setting       | Value                        |
| ------------- | ---------------------------- |
| Database File | `<InstallPath>\data\pacs.db` |
| Table Name    | `stored_instances`           |

Process:

1. Stop Gateway services.
2. Backup PACS database.
3. Archive PACS storage files.
4. Restart Gateway services.

---

# PACS Archive Process

After a successful PACS database backup:

## Source Directory

```text
<InstallPath>\data\storage
```

## Archive Location

```text
<InstallPath>\data\storage.zip
```

## Process

1. All files within the PACS storage directory are compressed into a ZIP archive.
2. Archive is written to `storage.zip`.
3. Original storage contents are deleted.
4. Archive operation is logged.

### Important

The archive operation removes all files from the PACS storage directory after successful compression.

---

# Log Rotation

Action:

```powershell
RotateLogs
```

The script rotates log files for each Gateway service.

Example:

```text
Gateway-MWL.log
```

becomes:

```text
Gateway-MWL.log.1
```

Existing rotations are shifted:

```text
Gateway-MWL.log.1 -> Gateway-MWL.log.2
Gateway-MWL.log.2 -> Gateway-MWL.log.3
...
Gateway-MWL.log.5 removed
```

## Retention Policy

* Maximum retained log generations: 5
* Oldest rotation is deleted before creating a new rotation

Process:

1. Stop Gateway services.
2. Rotate all service logs.
3. Restart Gateway services.

---

# Scheduled Tasks

The script registers three Windows Scheduled Tasks.

## MWL Database Maintenance

| Setting   | Value                     |
| --------- | ------------------------- |
| Task Name | `Gateway-MWL-Maintenance` |
| Schedule  | Weekly                    |
| Day       | Sunday                    |
| Time      | 02:00                     |
| User      | SYSTEM                    |
| Run Level | Highest                   |

Executed command:

```powershell
powershell.exe -ExecutionPolicy Bypass -File maintenance.ps1 -Action BackupMWLDatabase
```

---

## PACS Database Maintenance

| Setting   | Value                      |
| --------- | -------------------------- |
| Task Name | `Gateway-PACS-Maintenance` |
| Schedule  | Weekly                     |
| Day       | Sunday                     |
| Time      | 02:15                      |
| User      | SYSTEM                     |
| Run Level | Highest                    |

Executed command:

```powershell
powershell.exe -ExecutionPolicy Bypass -File maintenance.ps1 -Action BackupPACSDatabase
```

---

## Log Rotation Maintenance

| Setting   | Value                      |
| --------- | -------------------------- |
| Task Name | `Gateway-Logs-Maintenance` |
| Schedule  | Daily                      |
| Time      | 02:30                      |
| User      | SYSTEM                     |
| Run Level | Highest                    |

Executed command:

```powershell
powershell.exe -ExecutionPolicy Bypass -File maintenance.ps1 -Action RotateLogs
```

---

# Failure Handling

The script terminates when:

* A Gateway service cannot be stopped within the configured timeout.
* The database backup utility returns a non-zero exit code.
* An unhandled PowerShell exception occurs.

Errors are written to:

```text
<InstallPath>\logs\maintenance.log
```

and displayed on the console.

---

# Maintenance Workflow Summary

## MWL Backup

```text
Stop Services
    ↓
Backup MWL Database
    ↓
Start Services
```

## PACS Backup

```text
Stop Services
    ↓
Backup PACS Database
    ↓
Archive PACS Files
    ↓
Start Services
```

## Log Rotation

```text
Stop Services
    ↓
Rotate Logs
    ↓
Start Services
```

