@echo off
REM Extrae titulo/compositor de los MXL locales (solo lectura).
REM Uso: run_extract_mxl_metadata.bat --limit 1000
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

.\.venv\Scripts\python.exe scripts\extract_mxl_metadata.py %*
pause
