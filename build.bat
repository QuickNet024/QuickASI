@echo off
chcp 65001 >nul
echo Building WB亏损计算系统...
echo.

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Install pyinstaller if not present
pip install pyinstaller --quiet

:: Build
pyinstaller ^
    --name "WB亏损计算系统" ^
    --onefile ^
    --windowed ^
    --noconfirm ^
    --add-data "data;data" ^
    --add-data "src/ui/assets;src/ui/assets" ^
    --add-data "ico;ico" ^
    --hidden-import=src ^
    --hidden-import=src.config ^
    --hidden-import=src.models ^
    --hidden-import=src.services ^
    --hidden-import=src.ui ^
    --hidden-import=src.ui.interfaces ^
    --collect-all qt_material ^
    --exclude-module PySide6.Qt3DAnimation ^
    --exclude-module PySide6.Qt3DCore ^
    --exclude-module PySide6.Qt3DExtras ^
    --exclude-module PySide6.Qt3DInput ^
    --exclude-module PySide6.Qt3DLogic ^
    --exclude-module PySide6.Qt3DRender ^
    --exclude-module PySide6.QtBluetooth ^
    --exclude-module PySide6.QtCharts ^
    --exclude-module PySide6.QtConcurrent ^
    --exclude-module PySide6.QtDBus ^
    --exclude-module PySide6.QtDataVisualization ^
    --exclude-module PySide6.QtDesigner ^
    --exclude-module PySide6.QtGraphs ^
    --exclude-module PySide6.QtGraphsWidgets ^
    --exclude-module PySide6.QtHelp ^
    --exclude-module PySide6.QtHttpServer ^
    --exclude-module PySide6.QtLocation ^
    --exclude-module PySide6.QtMultimedia ^
    --exclude-module PySide6.QtMultimediaWidgets ^
    --exclude-module PySide6.QtNetworkAuth ^
    --exclude-module PySide6.QtNfc ^
    --exclude-module PySide6.QtPdf ^
    --exclude-module PySide6.QtPdfWidgets ^
    --exclude-module PySide6.QtPrintSupport ^
    --exclude-module PySide6.QtQuick ^
    --exclude-module PySide6.QtQuick3D ^
    --exclude-module PySide6.QtQuickControls2 ^
    --exclude-module PySide6.QtQuickTest ^
    --exclude-module PySide6.QtQuickWidgets ^
    --exclude-module PySide6.QtRemoteObjects ^
    --exclude-module PySide6.QtScxml ^
    --exclude-module PySide6.QtSensors ^
    --exclude-module PySide6.QtSerialBus ^
    --exclude-module PySide6.QtSerialPort ^
    --exclude-module PySide6.QtSpatialAudio ^
    --exclude-module PySide6.QtStateMachine ^
    --exclude-module PySide6.QtTest ^
    --exclude-module PySide6.QtTextToSpeech ^
    --exclude-module PySide6.QtUiTools ^
    --exclude-module PySide6.QtWebChannel ^
    --exclude-module PySide6.QtWebEngineCore ^
    --exclude-module PySide6.QtWebEngineQuick ^
    --exclude-module PySide6.QtWebEngineWidgets ^
    --exclude-module PySide6.QtWebSockets ^
    --exclude-module PySide6.QtWebView ^
    src\main.py

echo.
echo Build complete! Executable is in dist\
pause
