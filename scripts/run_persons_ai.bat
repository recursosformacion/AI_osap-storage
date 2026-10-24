@echo off
REM Genera y envia a Gemini los lotes de personas que aun no tienen respuesta.
REM Las cuatro claves se leen de secrets\gemini.prod.key (valor tras '=').
REM No escribe en la BD: las respuestas quedan en data\ai_out\ y luego se aplican
REM con scripts\apply_persons_ai_json.py.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

set "GEMINI_API_KEY="
set "GEMINI_API_KEY2="
set "GEMINI_API_KEYS="
for /f "tokens=2 delims==" %%A in (secrets\gemini.prod.key) do call :append_key "%%A"
if "%GEMINI_API_KEYS%"=="" (
  echo ERROR: no se encontraron claves en secrets\gemini.prod.key
  pause
  exit /b 1
)

echo Lanzando lotes desde el 6. Ctrl+C para parar; se reanuda saltando los ya hechos.
.\.venv\Scripts\python.exe scripts\persons_ai_runner.py --start 6 --sleep 2 %*
pause
goto :eof

:append_key
if defined GEMINI_API_KEYS (
  set "GEMINI_API_KEYS=%GEMINI_API_KEYS%;%~1"
) else (
  set "GEMINI_API_KEYS=%~1"
)
exit /b
