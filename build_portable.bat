@echo off
chcp 65001 >nul
echo ========================================
echo   WB亏损计算系统 - 便携版打包
echo ========================================
echo.

:: Activate virtual environment if exists
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else (
    echo WARNING: .venv not found, using system Python
)

:: Install pyinstaller if not present
pip install pyinstaller --quiet

:: Clean previous build
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo [1/3] Building exe with PyInstaller...
pyinstaller ^
    --name "WB亏损计算系统" ^
    --windowed ^
    --noconfirm ^
    --hidden-import=src ^
    --hidden-import=src.config ^
    --hidden-import=src.models ^
    --hidden-import=src.services ^
    --hidden-import=src.ui ^
    --hidden-import=src.ui.interfaces ^
    --collect-all PySide6 ^
    --collect-all qt_material ^
    src\main.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: PyInstaller build failed!
    pause
    exit /b 1
)

echo.
echo [2/3] Copying data files...
xcopy /E /I /Y "data" "dist\WB亏损计算系统\data"
xcopy /Y "启动.pyw" "dist\WB亏损计算系统\"

echo.
echo [3/3] Creating startup shortcut...
(
echo @echo off
echo chcp 65001 ^>nul
echo cd /d "%%~dp0"
echo start "" "WB亏损计算系统.exe"
) > "dist\WB亏损计算系统\启动.bat"

echo.
echo ========================================
echo   Build complete!
echo   Output: dist\WB亏损计算系统\
echo   Copy the entire folder to run.
echo ========================================
echo.
echo Folder contents:
dir /b "dist\WB亏损计算系统" 2>nul
echo.
pause
