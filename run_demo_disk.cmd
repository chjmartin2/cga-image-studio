@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist "artifacts\demo-slideshow\CGADEMO.DSK" (
    echo Demo disk not found. See docs\DEMO_DISK.md to build the 24 reviewed examples.
    popd
    exit /b 1
)
".venv\Scripts\python.exe" tools\open_marty.py "artifacts\demo-slideshow\CGADEMO.DSK" --rgb --runtime-root "artifacts\demo-slideshow\marty-runs"
set "CGA_DEMO_EXIT=%ERRORLEVEL%"
if not "%CGA_DEMO_EXIT%"=="0" pause
popd
exit /b %CGA_DEMO_EXIT%
