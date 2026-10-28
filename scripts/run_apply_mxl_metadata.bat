@echo off
REM Aplica el compositor MXL cuando ya existe una persona unica con ese nombre.
REM Por defecto DRY-RUN; para escribir: anade --apply.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

.\.venv\Scripts\python.exe scripts\apply_mxl_metadata.py %*
pause
