:: Backs up and resets the MWL worklist database. Intended to be run via Windows Task Scheduler.
:: Assumes the project venv is at .venv\ relative to the root directory (uv default).
:: Adjust the Python path below if the deployment creates the venv elsewhere.
@echo off
set rootdir=%~1
"%rootdir%\.venv\Scripts\python.exe" -m mwl_reset
