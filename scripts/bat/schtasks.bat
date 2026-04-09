:: Registers a daily scheduled task to back up and reset the MWL worklist database.
:: Default schedule: daily at 02:00. Adjust /st to change the time.
:: /f overwrites the task if it already exists.
@echo off
set thisdir=%~dp0
set rootdir="%thisdir%..\.."
schtasks /create /tn MWLDailyReset /tr "%thisdir%backup_database.bat %rootdir%" /sc daily /st 02:00 /f
