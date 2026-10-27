@echo off
REM Propone limpiar nombres de personas contaminados con titulos/URLs (solo lectura).
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

.\.venv\Scripts\python.exe scripts\clean_person_names.py %*
pause
