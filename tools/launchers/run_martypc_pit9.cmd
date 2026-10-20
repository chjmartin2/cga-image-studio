@echo off
setlocal
for %%I in ("%~dp0..\..") do set "CGA_STUDIO_ROOT=%%~fI"
pushd "%CGA_STUDIO_ROOT%"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" "tools\run_pit9_test.py" %*
set "PIT9_EXIT=%ERRORLEVEL%"
popd
exit /b %PIT9_EXIT%
