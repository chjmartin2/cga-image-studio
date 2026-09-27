@echo off
setlocal
"%~dp0.venv\Scripts\python.exe" "%~dp0tools\run_cga_disk.py" %*
if errorlevel 1 pause
