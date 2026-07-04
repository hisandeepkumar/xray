@echo off
echo =================================================
echo Building DICOM to Telegram executable...
echo =================================================
echo.
echo Installing required packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies. Check your internet or pip.
    pause
    exit /b 1
)
echo.
echo Creating standalone .exe (this may take a few minutes)...
pyinstaller --onefile --windowed --name DICOMtoTelegram main.py
if errorlevel 1 (
    echo PyInstaller build failed.
    pause
    exit /b 1
)
echo.
echo =================================================
echo Build successful!
echo The executable is located in the "dist" folder:
echo   dist\DICOMtoTelegram.exe
echo =================================================
pause
