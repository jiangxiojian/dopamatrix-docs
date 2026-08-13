@echo off
setlocal
python "%~dp0bitbrowser_rpa_example.py"
set "exit_code=%ERRORLEVEL%"
echo.
if not "%exit_code%"=="0" (
  echo Publisher finished with exit code %exit_code%.
) else (
  echo Draft preparation finished. Review the open browser tabs before publishing.
)
pause
exit /b %exit_code%
