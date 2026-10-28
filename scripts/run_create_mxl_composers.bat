@echo off
REM Crea personas desde compositores MXL limpios y asocia sus obras.
REM Por defecto DRY-RUN; para escribir: anade --apply.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

.\.venv\Scripts\python.exe scripts\create_mxl_composers.py %*
pause
