@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM  LTCtoMIDI — build script
REM  Run from the project root: build.bat
REM ─────────────────────────────────────────────────────────────────────────

echo [1/2] Installing / upgrading PyInstaller...
pip install --upgrade pyinstaller
if errorlevel 1 (
    echo.
    echo ERROR: pip failed. Make sure Python is in PATH.
    pause & exit /b 1
)

echo.
echo [2/2] Building LTCtoMIDI.exe ...
python -m PyInstaller --clean ltctomidi.spec

echo.
if errorlevel 1 (
    echo *** BUILD FAILED — see output above ***
) else (
    echo ─────────────────────────────────────────────────────────────
    echo  SUCCESS:  dist\LTCtoMIDI.exe
    echo ─────────────────────────────────────────────────────────────
)

pause
