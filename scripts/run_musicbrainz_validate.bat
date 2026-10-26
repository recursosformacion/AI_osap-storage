@echo off
REM Valida propuestas de Wikidata contra MusicBrainz (solo lectura).
REM Uso: run_musicbrainz_validate.bat --persons-file data\wikidata_persons\proposals_XXX.json
REM      run_musicbrainz_validate.bat --works-file data\wikidata_works\proposals_XXX.json --limit 50
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: falta .venv en osap-storage
  pause
  exit /b 1
)

.\.venv\Scripts\python.exe scripts\musicbrainz_validate.py %*
pause
