@echo off
REM Pipeline de OBRAS: genera lotes, los envia a Gemini y guarda respuestas.
REM No aplica a la BD. La aplicacion se hace con apply_works_ai_json.py.
REM Por defecto procesa todos los lotes. Usa --limit N para limitar.
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

echo Generando/enviando lotes de obras (20 por lote)...
.\.venv\Scripts\python.exe scripts\works_ai_runner.py --start 1 --limit 0 --sleep 2 %*
pause
goto :eof

:append_key
if defined GEMINI_API_KEYS (
  set "GEMINI_API_KEYS=%GEMINI_API_KEYS%;%~1"
) else (
  set "GEMINI_API_KEYS=%~1"
)
exit /b
