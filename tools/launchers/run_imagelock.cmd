@echo off
setlocal
for %%I in ("%~dp0..\..") do set "CGA_STUDIO_ROOT=%%~fI"
"%CGA_STUDIO_ROOT%\.venv\Scripts\python.exe" "%CGA_STUDIO_ROOT%\tools\run_imagelock.py" %*
set "IMAGELOCK_EXIT=%ERRORLEVEL%"
exit /b %IMAGELOCK_EXIT%
