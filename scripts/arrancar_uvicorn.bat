@echo off
title osap-storage uvicorn (dev)

REM Comprueba si uvicorn ya escucha en el puerto 8000
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo uvicorn ya esta corriendo en el puerto 8000.
  timeout /t 4 >nul
  exit /b 0
)

cd /d D:\Proyectos\AI_OSAP\osap-storage
set OSAP_CONFIG=D:\Proyectos\AI_OSAP\osap-storage\config.test.yaml
D:\Proyectos\AI_OSAP\osap-storage\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
