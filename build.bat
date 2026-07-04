@echo off
echo =================================================
echo Building DICOM to Telegram executable
echo =================================================

REM 1. Create and activate a virtual environment
echo Creating a virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

REM 2. Upgrade pip and install dependencies
echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

REM 3. Build with PyInstaller – सभी packages को पूरी तरह collect करें
echo Building .exe with PyInstaller...
pyinstaller --onefile --windowed ^
    --hidden-import numpy ^
    --hidden-import numpy._core ^
    --hidden-import numpy._core.multiarray ^
    --hidden-import pylibjpeg ^
    --hidden-import pylibjpeg_libjpeg ^
    --collect-all numpy ^
    --collect-all pydicom ^
    --collect-all pylibjpeg ^
    --collect-all pylibjpeg_libjpeg ^
    --collect-all img2pdf ^
    --name DICOMtoTelegram ^
    main.py

REM 4. Deactivate venv
call venv\Scripts\deactivate.bat

echo.
echo =================================================
echo Build completed!
echo Executable: dist\DICOMtoTelegram.exe
echo =================================================
pause
