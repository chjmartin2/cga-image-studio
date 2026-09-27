@echo off
setlocal
for %%I in ("%~dp0..") do set "VALIDATE_ROOT=%%~fI"
set "CARGO_HOME=%VALIDATE_ROOT%\external\marty-toolchain\cargo"
set "RUSTUP_HOME=%VALIDATE_ROOT%\external\marty-toolchain\rustup"
set "PATH=%CARGO_HOME%\bin;%PATH%"
for /f "usebackq delims=" %%I in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VALIDATE_VS=%%I"
call "%VALIDATE_VS%\Common7\Tools\VsDevCmd.bat" -no_logo -arch=x64 -host_arch=x64
if not exist "%VALIDATE_ROOT%\external\research\imagelock-validation\src" mkdir "%VALIDATE_ROOT%\external\research\imagelock-validation\src"
copy /y "%VALIDATE_ROOT%\tools\validate_imagelock.rs" "%VALIDATE_ROOT%\external\research\imagelock-validation\src\main.rs" >nul
copy /y "%VALIDATE_ROOT%\tools\validate_imagelock.Cargo.toml" "%VALIDATE_ROOT%\external\research\imagelock-validation\Cargo.toml" >nul
if not exist "%VALIDATE_ROOT%\external\research\imagelock-validation\Cargo.lock" copy /y "%VALIDATE_ROOT%\external\martypc\Cargo.lock" "%VALIDATE_ROOT%\external\research\imagelock-validation\Cargo.lock" >nul
cargo build --offline --release --manifest-path "%VALIDATE_ROOT%\external\research\imagelock-validation\Cargo.toml" --target-dir "%VALIDATE_ROOT%\external\research\imagelock-validation\target"
if errorlevel 1 exit /b 1
"%VALIDATE_ROOT%\external\research\imagelock-validation\target\release\validate_imagelock.exe" "%VALIDATE_ROOT%" %*


