@echo off
REM Valida con Gemini los nombres contaminados y propone/aplica limpieza.
REM Por defecto no escribe; para aplicar: anade --apply.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

.\.venv\Scripts\python.exe scripts\validate_cleanup_ai.py %*
pause
