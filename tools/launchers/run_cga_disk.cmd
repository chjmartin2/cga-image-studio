@echo off
setlocal
for %%I in ("%~dp0..\..") do set "CGA_STUDIO_ROOT=%%~fI"
"%CGA_STUDIO_ROOT%\.venv\Scripts\python.exe" "%CGA_STUDIO_ROOT%\tools\run_cga_disk.py" %*
set "CGA_DISK_EXIT=%ERRORLEVEL%"
if not "%CGA_DISK_EXIT%"=="0" pause
exit /b %CGA_DISK_EXIT%
