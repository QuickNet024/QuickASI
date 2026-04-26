# -*- coding: utf-8 -*-
"""
WB亏损计算系统 - 应用入口
"""
import sys
import os
import threading

# Ensure the project root is in Python path
# Support both development and PyInstaller frozen modes
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle — use exe directory as project root
    _PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    # Development mode — use project root (parent of src/)
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.ui.main_window import MainWindow
from src.ui.theme_manager import ThemeManager


def main():
    # PySide6 / Qt6 handles HiDPI automatically — no AA_ attributes needed
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Set application font
    font = app.font()
    font.setFamily("Microsoft YaHei")
    font.setPointSize(9)
    app.setFont(font)

    # Apply saved theme
    tm = ThemeManager()
    tm.apply_theme(app)

    window = MainWindow()
    window.show()

    def cleanup():
        from src.ui.debug_log_window import DebugLogManager
        mgr = DebugLogManager()
        if mgr:
            mgr.shutdown()

    app.aboutToQuit.connect(cleanup)

    exit_code = app.exec()

    # Safety net: force-kill process after 5 seconds if non-daemon threads
    # (e.g. ThreadPoolExecutor in feishu_service) refuse to stop
    force_timer = threading.Timer(5.0, lambda: os._exit(0))
    force_timer.daemon = True
    force_timer.start()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
