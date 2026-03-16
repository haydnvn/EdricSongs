@echo off
title Building Track Splitter...
echo ============================================
echo   Track Splitter - EXE Builder
echo ============================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo [1/4] Installing dependencies...
pip install pyinstaller pillow --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo [2/4] Converting icon.png to icon.ico...
python -c "from PIL import Image; img = Image.open('icon.png').convert('RGBA'); img.save('icon.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if errorlevel 1 (
    echo WARNING: Icon conversion failed, building without icon.
    set ICON_FLAG=
) else (
    set ICON_FLAG=--icon icon.ico
)

echo [3/4] Clearing old build cache...
if exist build rmdir /s /q build
if exist "Track Splitter.spec" del /q "Track Splitter.spec"
if exist dist rmdir /s /q dist

echo [3/4] Building EXE (this may take 30-60 seconds)...
pyinstaller --onefile --windowed --name "Track Splitter" %ICON_FLAG% --add-data "icon.png;." track_splitter_gui.py
if errorlevel 1 (
    echo.
    echo ERROR: Build failed. Check the output above for details.
    pause
    exit /b 1
)

echo [4/4] Cleaning up build files...
if exist build rmdir /s /q build
if exist "Track Splitter.spec" del /q "Track Splitter.spec"

echo.
echo ============================================
echo   Your EXE is ready:
echo   dist\Track Splitter.exe
echo ============================================
echo.
echo Opening dist folder...
explorer dist

pause
