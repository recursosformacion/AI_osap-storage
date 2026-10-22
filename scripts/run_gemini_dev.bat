@echo off
REM Lanza el script existente de revisión con Gemini contra la BD DE DESARROLLO.
REM Requisitos: osap-storage\config.yaml apuntando a osap_storage local (3306) y
REM las claves en secrets\gemini.key (dev) y secrets\gemini.prod.key (segunda clave).
REM Solo genera propuestas; NO aplica cambios. Revisar docs\ai\reviews_dev.json y,
REM si procede, ejecutar a mano --apply.
setlocal
cd /d D:\Proyectos\AI_OSAP\osap-storage

if not exist docs\ai mkdir docs\ai

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
  echo ERROR: falta secrets\gemini.key
  pause
  exit /b 1
)

echo Generando lista de nombres desde la BD local de desarrollo...
.\.venv\Scripts\python.exe -c "import pymysql,yaml; c=(yaml.safe_load(open('config.yaml',encoding='utf-8')) or {})['db']; cn=pymysql.connect(host=c.get('host','127.0.0.1'),port=int(c.get('port',3306)),user=c.get('user'),password=c.get('password'),database=c.get('name'),charset='utf8mb4'); cur=cn.cursor(); cur.execute(\"SELECT DISTINCT persons_name FROM persons WHERE persons_name IS NOT NULL AND persons_name != '' AND (persons_review_status IS NULL OR persons_review_status != 'reviewed') ORDER BY persons_name LIMIT 200\"); rows=[r[0] for r in cur.fetchall()]; open('docs/ai/names_dev.txt','w',encoding='utf-8').write('\n'.join(rows)); print(f'{len(rows)} nombres')"
if errorlevel 1 (
  echo ERROR generando names_dev.txt
  pause
  exit /b 1
)

if /i "%SKIP_GEMINI%"=="1" (
  echo SKIP_GEMINI=1: no se llama a Gemini.
  type docs\ai\names_dev.txt
  exit /b 0
)

echo Consultando a Gemini (2 claves, solo propuestas)...
.\.venv\Scripts\python.exe scripts\review_persons_ai.py --generate --names-file docs\ai\names_dev.txt --out docs\ai\reviews_dev.json --limit 200
if errorlevel 1 (
  echo ERROR en la fase --generate
  pause
  exit /b 1
)

echo.
echo Propuestas en docs\ai\reviews_dev.json
echo Revisar y, si procede: .\.venv\Scripts\python.exe scripts\review_persons_ai.py --apply docs\ai\reviews_dev.json --commit
pause
