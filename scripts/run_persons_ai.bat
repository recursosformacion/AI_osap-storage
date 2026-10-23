@echo off
REM Genera y envia a Gemini los lotes de personas que aun no tienen respuesta.
REM Las claves se leen de secrets\gemini.key y secrets\gemini.prod.key (valor tras '=').
REM No escribe en la BD: las respuestas quedan en data\ai_out\ y luego se aplican
REM con scripts\apply_persons_ai_json.py.
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

echo Lanzando lotes desde el 6. Ctrl+C para parar; se reanuda saltando los ya hechos.
.\.venv\Scripts\python.exe scripts\persons_ai_runner.py --start 6 --sleep 2 %*
pause
