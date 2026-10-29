@echo off
REM Pipeline de OBRAS con Groq (free). Lee las claves de osap-api\docs\secrets.
REM Groq free tiene TPM 8000: se envian 5 obras por llamada y se espera 35s entre chunks.
REM No escribe en la BD. Aplicar despues con apply_works_ai_json.py.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

for /f "tokens=2 delims==" %%A in ('findstr /b /i "groq =" "D:\Proyectos\AI_OSAP\osap-api\docs\secrets"') do (
  set "GROQ_API_KEY=%%A"
  goto :key_done
)
:key_done
if "%GROQ_API_KEY%"=="" (
  echo ERROR: falta la clave groq en osap-api\docs\secrets
  pause
  exit /b 1
)
REM Quita espacios iniciales de la clave (findstr deja el espacio tras '=')
for /f "tokens=* delims= " %%A in ("%GROQ_API_KEY%") do set "GROQ_API_KEY=%%A"

set "LLM_PROVIDER=groq"
set "LLM_MODEL=openai/gpt-oss-120b"
echo Lotes de 5 obras; 35s entre llamadas. Ctrl+C para parar (reanudable).
.\.venv\Scripts\python.exe scripts\works_ai_runner.py --start 3 --limit 100 --chunk 5 --sleep 35 %*
pause
