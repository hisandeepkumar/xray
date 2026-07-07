@echo off
title DICOM to PDF - Setup & Build
color 0A
cd /d "%~dp0"

echo =============================================
echo  STEP 1: Checking for Python...
echo =============================================

:: Check if python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Trying python launcher (py)...
    py -3 --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [ERROR] Python is NOT installed on this system.
        echo Please install Python from python.org (Make sure to check "Add to PATH").
        echo.
        pause
        exit /b
    ) else (
        set PYTHON_CMD=py -3
    )
) else (
    set PYTHON_CMD=python
)

echo Using command: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.
pause

echo =============================================
echo  STEP 2: Installing Required Libraries...
echo =============================================

%PYTHON_CMD% -m pip install --upgrade pip
%PYTHON_CMD% -m pip install pydicom pillow img2pdf pyinstaller numpy

if errorlevel 1 (
    echo.
    echo [ERROR] Package installation failed. Check your internet.
    pause
    exit /b
)

echo.
echo Packages installed successfully.
pause

echo =============================================
echo  STEP 3: Building EXE file...
echo =============================================

%PYTHON_CMD% -m PyInstaller --onefile --windowed --name "DICOMtoPDF" dicom_to_pdf_gui.py

if exist dist\DICOMtoPDF.exe (
    echo.
    echo =============================================
    echo  [SUCCESS] EXE created successfully!
    echo  Location: "%~dp0dist\DICOMtoPDF.exe"
    echo =============================================
) else (
    echo.
    echo =============================================
    echo  [FAILED] Build failed. Check errors above.
    echo =============================================
)

echo.
echo Press ANY key to close this window...
pause >nul
exit
