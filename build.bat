@echo off
title RAD-XR Pro Compiler Hub
echo ===================================================
echo  RAD-XR - Fully Patched Production Compiler Stack
echo ===================================================
echo.

:: Step 1: Clean old build data
echo [1/4] Flushing existing binary cache...
rmdir /s /q build dist
del /q RAD-XR.spec
echo Done.

:: Step 2: Install and refresh exact patched environment packages
echo [2/4] Initializing exact dependency parameters...
pip install -r requirements.txt --force-reinstall
if %errorlevel% neq 0 (
    echo ERROR: Library download layer failed.
    pause
    exit /b
)
echo Packages loaded successfully.
echo.

:: Step 3: Compile with deep data mapping structures
echo [3/4] Packing deployment binary as RAD-XR.exe...
pyinstaller --noconsole --onefile --name="RAD-XR" --collect-all pydicom --collect-all pynetdicom --collect-all pylibjpeg --collect-data pydicom --hidden-import=numpy --hidden-import=pynetdicom --hidden-import=pydicom.encoders.gdcm --hidden-import=pydicom.encoders.pylibjpeg --hidden-import=pylibjpeg --hidden-import=pylibjpeg.utils --hidden-import=openjpeg app.py
if %errorlevel% neq 0 (
    echo.
    echo ERROR: PyInstaller compilation process collapsed.
    pause
    exit /b
)
echo.

:: Step 4: Finished
echo [4/4] Patched RAD-XR.exe generated! Check 'dist' directory.
pause
