@echo off
setlocal

if "%~1"=="" (
  echo Enter publish_plan.csv path, or drag publish_plan.csv onto this file.
  set /p PLAN_CSV=Plan CSV: 
) else (
  set "PLAN_CSV=%~1"
)

if "%PLAN_CSV%"=="" (
  echo No publish_plan.csv provided.
  pause
  exit /b 1
)

python "%~dp0rpa_workbench_server.py" --plan-csv "%PLAN_CSV%" --open-browser
set "exit_code=%ERRORLEVEL%"
echo.
echo Workbench finished with exit code %exit_code%.
pause
exit /b %exit_code%
