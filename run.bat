@echo off
setlocal
set "HERE=%~dp0"
if not exist "%HERE%build\port\bin\rozu.exe" (
    echo The game has not been built yet. Run Tools/generate.py and build.bat first.
    pause
    exit /b 1
)
"%HERE%build\port\bin\rozu.exe" %*
