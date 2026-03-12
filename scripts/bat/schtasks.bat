:: This batch file creates a scheduled task to run the backup_database.bat script daily at midnight.
@echo off
set thisdir=%~dp0
set rootdir="%thisdir%..\.."
schtasks /create /tn BackupDatabaseTask /tr "%thisdir%backup_database.bat %rootdir%" /sc daily /st 00:00
