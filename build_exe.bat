@echo off
setlocal
cd /d "%~dp0"
where pyinstaller >nul 2>&1
if errorlevel 1 (
  echo PyInstaller was not found. Install it with: python -m pip install pyinstaller
  exit /b 1
)
if not exist cpp_engine.cp312-win_amd64.pyd (
  echo Warning: optional cpp_engine.cp312-win_amd64.pyd was not found. The normal converter can still build.
)
if exist build\pyinstaller rmdir /s /q build\pyinstaller
if exist dist\FileConverterEngine.exe del /q dist\FileConverterEngine.exe
pyinstaller --noconfirm --clean --workpath build\pyinstaller --distpath dist FileConverterEngine.spec
if errorlevel 1 (
  echo PyInstaller build failed.
  exit /b 1
)
echo.
echo Built: %~dp0dist\FileConverterEngine.exe
echo LibreOffice and Microsoft Office remain external runtime prerequisites.
endlocal
