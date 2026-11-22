@echo off
setlocal
pushd "%~dp0"

python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo PyInstaller was not found.
  echo Install dependencies with: python -m pip install -r requirements.txt
  popd
  pause
  exit /b 1
)

if not exist build mkdir build
if not exist dist mkdir dist

python -m PyInstaller --noconfirm --clean --onedir --windowed --name DopaMatrixPublisher --collect-all playwright --collect-all tzdata --hidden-import requests dopa_matrix_publisher.py

set "exit_code=%ERRORLEVEL%"
echo.
if "%exit_code%"=="0" (
  if exist "..\..\product-ops\15-rpa-operator-quickstart.txt" copy /Y "..\..\product-ops\15-rpa-operator-quickstart.txt" "%~dp0dist\DopaMatrixPublisher\README.txt" >nul
  echo Build complete: %~dp0dist\DopaMatrixPublisher\DopaMatrixPublisher.exe
  echo Distribute the whole DopaMatrixPublisher folder, not the EXE alone.
  echo A plain-text operator guide is included as README.txt.
) else (
  echo Build failed with exit code %exit_code%.
)
popd
pause
exit /b %exit_code%
