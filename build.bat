@echo off
setlocal

echo.
echo Aylo build
echo ===============
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    pause
    exit /b 1
)

python build.py
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Review the output above.
    pause
    exit /b 1
)

echo.
echo [OK] Build complete: dist\Aylo.exe
pause
