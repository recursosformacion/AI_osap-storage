@echo off
REM Pipeline de OBRAS: genera lotes, los envia a Gemini y guarda respuestas.
REM No aplica a la BD. La aplicacion se hace con apply_works_ai_json.py.
REM Por defecto procesa 10 lotes (200 obras). Usa --limit 0 para todos.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

for /f "tokens=2 delims==" %%A in (secrets\gemini.key) do (
  set "GEMINI_API_KEY=%%A"
  goto :key1_done
)
:key1_done
for /f "skip=1 tokens=2 delims==" %%A in (secrets\gemini.prod.key) do (
  set "GEMINI_API_KEY2=%%A"
  goto :key2_done
)
:key2_done
if "%GEMINI_API_KEY%"=="" (
  echo ERROR: falta la clave en secrets\gemini.key
  pause
  exit /b 1
)

echo Generando/enviando lotes de obras (20 por lote)...
.\.venv\Scripts\python.exe scripts\works_ai_runner.py --start 1 --limit 10 --sleep 2 %*
pause
