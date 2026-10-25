@echo off
REM Consulta Wikidata (SPARQL) para completar obras cuyo compositor tiene QID.
REM No escribe en la BD: genera propuestas JSON/CSV en data\wikidata_works\.
REM Uso: run_wikidata_works.bat [--limit N] [--offset N] [--out ruta.json]
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

echo Consultando Wikidata para obras. Limite por defecto: 50 obras.
.\.venv\Scripts\python.exe scripts\wikidata_works.py --limit 50 %*
pause
