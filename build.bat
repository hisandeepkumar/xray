@echo off
title RAD-XR Ultimate Engine Compiler
echo ===================================================
echo  RAD-XR - Modern Automation Compiler Stack
echo ===================================================
echo.

:: Step 1: Flush environment cache
echo [1/4] Flushing existing build data files...
rmdir /s /q build dist
del /q RAD-XR.spec
echo Done.

:: Step 2: Sync python dependency bundles
echo [2/4] Syncing core dependencies...
pip install -r requirements.txt --force-reinstall
if %errorlevel% neq 0 (
    echo ERROR: Dependency mapping process collapsed.
    pause
    exit /b
)
echo.

:: Step 3: Bundle stand-alone distribution 
echo [3/4] Compiling secure binary execution node...
pyinstaller --noconsole --onefile --name="RAD-XR" --collect-all pydicom --collect-all pynetdicom --collect-all pylibjpeg --collect-data pydicom --hidden-import=numpy --hidden-import=pynetdicom --hidden-import=pydicom.encoders.gdcm --hidden-import=pydicom.encoders.pylibjpeg --hidden-import=pylibjpeg --hidden-import=pylibjpeg.utils --hidden-import=openjpeg app.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Binary bundling collapsed.
    pause
    exit /b
)
echo.

:: Step 4: Complete
echo [4/4] Execution completed! Standalone RAD-XR.exe ready inside 'dist' directory.
pause
