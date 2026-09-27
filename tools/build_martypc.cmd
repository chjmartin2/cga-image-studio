@echo off
setlocal
for %%I in ("%~dp0..") do set "MARTY_WORKSPACE=%%~fI"
set "MARTY_SOURCE=%MARTY_WORKSPACE%\external\martypc"
set "MARTY_TOOLS=%MARTY_WORKSPACE%\external\marty-toolchain"
set "CARGO_HOME=%MARTY_TOOLS%\cargo"
set "RUSTUP_HOME=%MARTY_TOOLS%\rustup"
set "LIBCLANG_PATH=%MARTY_TOOLS%\clang\clang\native"
set "MARTY_VSWHERE_DIR=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer"
set "PATH=%CARGO_HOME%\bin;%MARTY_VSWHERE_DIR%;%PATH%"
if not exist "%CARGO_HOME%\bin\cargo.exe" (
    echo The isolated Rust toolchain is missing. See docs\MARTYPC_BUILD.md.
    exit /b 1
)
if not exist "%LIBCLANG_PATH%\libclang.dll" (
    echo The isolated libclang library is missing. See docs\MARTYPC_BUILD.md.
    exit /b 1
)
if not exist "%MARTY_SOURCE%\Cargo.lock" (
    echo The MartyPC checkout is missing. See docs\MARTYPC_BUILD.md.
    exit /b 1
)
for /f "usebackq delims=" %%I in (`"%MARTY_VSWHERE_DIR%\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "MARTY_VS=%%I"
if not defined MARTY_VS (
    echo MSVC C++ build tools were not found. See docs\MARTYPC_BUILD.md.
    exit /b 1
)
call "%MARTY_VS%\Common7\Tools\VsDevCmd.bat" -no_logo -arch=x64 -host_arch=x64
if errorlevel 1 exit /b 1
pushd "%MARTY_SOURCE%"
if errorlevel 1 exit /b 1
cargo build --locked --release -p martypc_eframe --bin martypc
set "MARTY_EXIT=%ERRORLEVEL%"
if "%MARTY_EXIT%"=="0" git log -1 --format="Built commit: %%H (%%ci)"
popd
exit /b %MARTY_EXIT%
