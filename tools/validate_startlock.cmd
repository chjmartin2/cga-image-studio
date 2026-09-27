@echo off
setlocal
for %%I in ("%~dp0..") do set "VALIDATE_ROOT=%%~fI"
set "CARGO_HOME=%VALIDATE_ROOT%\external\marty-toolchain\cargo"
set "RUSTUP_HOME=%VALIDATE_ROOT%\external\marty-toolchain\rustup"
set "PATH=%CARGO_HOME%\bin;%PATH%"
for /f "usebackq delims=" %%I in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VALIDATE_VS=%%I"
call "%VALIDATE_VS%\Common7\Tools\VsDevCmd.bat" -no_logo -arch=x64 -host_arch=x64
if not exist "%VALIDATE_ROOT%\external\research\startlock-validation\src" mkdir "%VALIDATE_ROOT%\external\research\startlock-validation\src"
copy /y "%VALIDATE_ROOT%\tools\validate_startlock.rs" "%VALIDATE_ROOT%\external\research\startlock-validation\src\main.rs" >nul
copy /y "%VALIDATE_ROOT%\tools\validate_startlock.Cargo.toml" "%VALIDATE_ROOT%\external\research\startlock-validation\Cargo.toml" >nul
if not exist "%VALIDATE_ROOT%\external\research\startlock-validation\Cargo.lock" copy /y "%VALIDATE_ROOT%\external\martypc\Cargo.lock" "%VALIDATE_ROOT%\external\research\startlock-validation\Cargo.lock" >nul
cargo build --offline --release --manifest-path "%VALIDATE_ROOT%\external\research\startlock-validation\Cargo.toml" --target-dir "%VALIDATE_ROOT%\external\research\startlock-validation\target"
if errorlevel 1 exit /b 1
"%VALIDATE_ROOT%\external\research\startlock-validation\target\release\validate_startlock.exe" "%VALIDATE_ROOT%" %*

