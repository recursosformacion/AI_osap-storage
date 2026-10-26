@echo off
REM Consulta Wikidata (SPARQL) para completar personas incompletas.
REM No escribe en la BD: genera propuestas JSON/CSV en data\wikidata_persons\.
REM Uso: run_wikidata_persons.bat [--limit N] [--name-fallback] [--person-id UUID]
REM Recomendado no usar --limit 0 de golpe: Wikidata limita las consultas; usa lotes.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

echo Consultando Wikidata. Limite por defecto: 50 personas.
.\.venv\Scripts\python.exe scripts\wikidata_persons.py --limit 50 %*
pause

