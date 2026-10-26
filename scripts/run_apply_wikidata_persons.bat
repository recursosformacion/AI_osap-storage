@echo off
REM Aplica propuestas de Wikidata sobre personas (solo campos vacios).
REM Por defecto DRY-RUN. Para escribir: anade --apply.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

.\.venv\Scripts\python.exe scripts\apply_wikidata_persons.py --dry-run %*
pause
