@echo off
setlocal
pushd "%~dp0"
".venv\Scripts\python.exe" "tools\run_pit9_test.py" %*
set "PIT9_EXIT=%ERRORLEVEL%"
popd
exit /b %PIT9_EXIT%
