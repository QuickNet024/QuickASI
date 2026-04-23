@echo off
echo Building WB亏损计算系统...
echo.

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Install pyinstaller if not present
pip install pyinstaller --quiet

:: Build
pyinstaller ^
    --name "WB亏损计算系统" ^
    --windowed ^
    --noconfirm ^
    --add-data "data;data" ^
    --hidden-import=src ^
    --hidden-import=src.config ^
    --hidden-import=src.models ^
    --hidden-import=src.services ^
    --hidden-import=src.ui ^
    --collect-all PyQt5 ^
    src\main.py

echo.
echo Build complete! Executable is in dist\WB亏损计算系统\
pause
