@echo off
title DICOM to PDF Converter - Setup & Build

echo =============================================
echo  Checking for Python...
echo =============================================

python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Installing Python...
    echo Downloading Python 3.10.11 (64-bit)...
    powershell -Command "Invoke-WebRequest -Uri https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe -OutFile python_installer.exe"
    if exist python_installer.exe (
        echo Installing Python silently (this may take a few minutes)...
        start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
        del python_installer.exe
        echo Python installed successfully.
    ) else (
        echo Failed to download Python installer.
        echo Please install Python manually from python.org (add to PATH).
        pause
        exit /b
    )
) else (
    echo Python is already installed.
)

echo =============================================
echo  Checking pip...
echo =============================================
pip --version >nul 2>&1
if errorlevel 1 (
    echo pip not found, installing...
    python -m ensurepip --upgrade
)

echo =============================================
echo  Installing required packages...
echo =============================================
pip install pydicom pillow img2pdf pyinstaller numpy

if errorlevel 1 (
    echo Package installation failed. Check your internet connection.
    pause
    exit /b
)

echo =============================================
echo  Building executable with PyInstaller...
echo =============================================
pyinstaller --onefile --windowed --name "DICOMtoPDF" dicom_to_pdf_gui.py

if exist dist\DICOMtoPDF.exe (
    echo =============================================
    echo  Build successful!
    echo  Executable is in the "dist" folder.
    echo =============================================
) else (
    echo =============================================
    echo  Build failed. Please check errors above.
    echo =============================================
)

pause
