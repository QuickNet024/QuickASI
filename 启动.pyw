# -*- coding: utf-8 -*-
"""WB亏损计算系统 — 无控制台窗口启动入口
双击此文件或用 pythonw.exe 运行，不会弹出 CMD 窗口。
"""
import sys
import os
import threading

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.ui.main_window import MainWindow
from src.ui.theme_manager import ThemeManager


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    font = app.font()
    font.setFamily("Microsoft YaHei")
    font.setPointSize(9)
    app.setFont(font)

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
