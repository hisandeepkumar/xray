@echo off
title DICOM to PDF Builder
echo ===================================================
echo  DICOM to PDF - EXE installer Script
echo ===================================================
echo.

:: Step 1: Install Python Dependencies
echo [1/3] Dependencies install ho rahi hain...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python ya pip sahi se installed nahi hai ya internet disconnect hai.
    pause
    exit /b
)
echo Dependencies successfully install ho gayi hain.
echo.

:: Step 2: Build EXE using PyInstaller
echo [2/3] Software ki .exe file banayi ja rahi hai...
pyinstaller --noconsole --onefile app.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build process fail ho gaya.
    pause
    exit /b
)
echo.

:: Step 3: Cleanup and Finish
echo [3/3] Build poora hua! Apni exe file check karein.
echo Inside your folder:
echo - 'dist' folder ke andar aapko 'app.exe' mil jayegi.
echo - Aap 'build' folder aur 'app.spec' file ko delete kar sakte hain.
echo.
pause
