@echo off
title RAD-XR Enterprise Builder
echo ===================================================
echo  RAD-XR - DICOM Router Engine Compiler
echo ===================================================
echo.

:: Step 1: Install Python Dependencies
echo [1/3] Refreshing project network dependencies...
pip install -r requirements.txt --force-reinstall
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Dependency resolution failed.
    pause
    exit /b
)
echo Dependencies successfully loaded.
echo.

:: Step 2: Build Server EXE with RAD-XR Name
echo [2/3] Compiling Binary package as RAD-XR.exe...
pyinstaller --noconsole --onefile --name="RAD-XR" --collect-all numpy --collect-all pynetdicom --hidden-import=numpy --hidden-import=pynetdicom --hidden-import=pydicom.encoders.gdcm --hidden-import=pydicom.encoders.pylibjpeg --hidden-import=pylibjpeg --hidden-import=openjpeg app.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: PyInstaller compilation crashed.
    pause
    exit /b
)
echo.

:: Step 3: Finished
echo [3/3] RAD-XR System Engine Generated! Check 'dist' directory.
pause
