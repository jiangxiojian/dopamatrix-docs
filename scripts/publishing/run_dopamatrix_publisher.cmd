@echo off
setlocal
pushd "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Use the packaged DopaMatrixPublisher.exe, or install Python first.
  popd
  pause
  exit /b 1
)

python "%~dp0dopa_matrix_publisher.py"
set "exit_code=%ERRORLEVEL%"
if not "%exit_code%"=="0" (
  echo.
  echo DopaMatrix Publisher exited with code %exit_code%.
  popd
  pause
  exit /b %exit_code%
)
popd
exit /b %exit_code%
