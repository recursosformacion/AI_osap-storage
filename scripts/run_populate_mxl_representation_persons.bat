@echo off
REM Enlaza creadores MXL con representation_persons.
REM Por defecto DRY-RUN; para escribir: anade --apply.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

.\.venv\Scripts\python.exe scripts\populate_mxl_representation_persons.py %*
pause
