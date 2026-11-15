@echo off
setlocal
set "PY=%~dp0venv\Scripts\pythonw.exe"
if not exist "%PY%" set "PY=pythonw"
start "" "%PY%" "%~dp0main.py"
endlocal
