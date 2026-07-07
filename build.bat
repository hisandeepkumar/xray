@echo off
title RAD-XR Enterprise Hub Compiler
echo ===================================================
echo  RAD-XR - Modern Automation Compiler Stack
echo ===================================================
echo.

:: Step 1: Install Python Dependencies
echo [1/3] Parsing environment dependencies objects...
pip install -r requirements.txt --force-reinstall
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Library indexing failed.
    pause
    exit /b
)
echo Python environment packages configured successfully.
echo.

:: Step 2: Build Server EXE with RAD-XR Name
echo [2/3] Packing standalone deployment binary node...
pyinstaller --noconsole --onefile --name="RAD-XR" --collect-all numpy --collect-all pynetdicom --hidden-import=numpy --hidden-import=pynetdicom --hidden-import=pydicom.encoders.gdcm --hidden-import=pydicom.encoders.pylibjpeg --hidden-import=pylibjpeg --hidden-import=openjpeg app.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Binary compilation process collapsed.
    pause
    exit /b
)
echo.

:: Step 3: Finished
echo [3/3] Standalone RAD-XR.exe distribution compiled! Open dist folder.
pause
