:: Batch file to run the backup_database.py script
@echo off
set %rootdir=%1
python "%rootdir%\scripts\python\backup_database.py"
