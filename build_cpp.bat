@echo off
setlocal
cd /d "%~dp0"
python -m pip show pybind11 >nul 2>&1
if errorlevel 1 (
  echo pybind11 is not installed. Run: python -m pip install pybind11
  exit /b 1
)
for /f "delims=" %%i in ('python -m pybind11 --cmakedir') do set "PYBIND11_DIR=%%i"
if not defined PYBIND11_DIR (
  echo Could not locate pybind11's CMake configuration.
  exit /b 1
)
cmake -S cpp_engine -B cpp_engine\build -Dpybind11_DIR="%PYBIND11_DIR%"
if errorlevel 1 exit /b 1
cmake --build cpp_engine\build --config Release
if errorlevel 1 exit /b 1
echo.
echo C++ extension build completed. The module should be beside main.py.
echo Run: python test_cpp.py
endlocal
