@echo off
setlocal
for %%I in ("%~dp0..\..") do set "CGA_STUDIO_ROOT=%%~fI"
set "MARTY_INSTALL=%CGA_STUDIO_ROOT%\external\martypc\install"
set "MARTY_EXE=%CGA_STUDIO_ROOT%\external\martypc\target\release\martypc.exe"
if not exist "%MARTY_EXE%" (
    echo MartyPC has not been built. See docs\MARTYPC_BUILD.md.
    exit /b 1
)
if not exist "%MARTY_INSTALL%\martypc-cga.toml" (
    echo The local CGA configuration is missing. See docs\MARTYPC_BUILD.md.
    exit /b 1
)
pushd "%MARTY_INSTALL%"
if errorlevel 1 exit /b 1
"%MARTY_EXE%" --configfile "%MARTY_INSTALL%\martypc-cga.toml" %*
set "MARTY_EXIT=%ERRORLEVEL%"
popd
exit /b %MARTY_EXIT%
