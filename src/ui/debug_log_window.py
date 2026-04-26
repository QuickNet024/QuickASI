# -*- coding: utf-8 -*-
"""调试日志窗口 — 独立窗口实时显示飞书同步日志

特性:
- 实时滚动显示日志
- 按级别过滤 (DEBUG/INFO/WARNING/ERROR)
- 关键词搜索过滤
- 暂停/继续自动滚动
- 清空日志
- 导出日志到文件
"""

import os
import logging
import threading
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QComboBox, QLabel, QLineEdit, QFileDialog,
    QCheckBox
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QTextCursor, QColor, QTextCharFormat, QFont

logger = logging.getLogger(__name__)


# ═══ 信号桥（线程安全推送到 UI）══════════════════

class _LogSignalBridge(QObject):
    """将 logging 记录通过 Signal 传到主线程"""
    log_record = Signal(str, int)  # (formatted_message, levelno)


# ═══ Qt 日志 Handler ════════════════════════════

class QtLogHandler(logging.Handler):
    """自定义 logging Handler — 将日志推送到 DebugLogWindow。

    用法:
        handler = QtLogHandler()
        handler.signal_bridge.log_record.connect(window.append_log)
        logging.getLogger("src.services.feishu_service").addHandler(handler)
    """

    def __init__(self):
        super().__init__()
        self.signal_bridge = _LogSignalBridge()
        self.setLevel(logging.DEBUG)
        # 格式: [时间] [级别] 消息
        self.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        ))

    def emit(self, record):
        try:
            msg = self.format(record)
            self.signal_bridge.log_record.emit(msg, record.levelno)
        except Exception:
            pass


# ═══ 文件日志 Handler ════════════════════════════

class FileLogHandler(logging.Handler):
    """将日志写入文件的 Handler。"""

    def __init__(self, log_dir="data/logs"):
        super().__init__()
        self._log_dir = log_dir
        self._lock = threading.Lock()
        self.setLevel(logging.DEBUG)
        self.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        os.makedirs(log_dir, exist_ok=True)

    def emit(self, record):
        try:
            msg = self.format(record)
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_path = os.path.join(self._log_dir, f"feishu_sync_{date_str}.log")
            with self._lock:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
        except Exception:
            pass


# ═══ 调试日志窗口 ════════════════════════════════

class DebugLogWindow(QWidget):
    """独立窗口 — 实时显示飞书同步调试日志"""

    # 级别颜色
    _LEVEL_COLORS = {
        logging.DEBUG:    "#80868B",  # 灰色
        logging.INFO:     "#E8EAED",  # 浅色（暗色主题下清晰）
        logging.WARNING:  "#FBBC04",  # 黄色
        logging.ERROR:    "#F28B82",  # 红色
        logging.CRITICAL: "#EE675C",  # 亮红
    }

    # 浅色主题下的颜色
    _LEVEL_COLORS_LIGHT = {
        logging.DEBUG:    "#9AA0A6",
        logging.INFO:     "#202124",
        logging.WARNING:  "#E37400",
        logging.ERROR:    "#D93025",
        logging.CRITICAL: "#C5221F",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False
        self._auto_scroll = True
        self._min_level = logging.DEBUG
        self._filter_text = ""
        self._is_dark = True  # 跟随主题
        self._log_count = 0
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("调试日志 — 飞书同步")
        self.setMinimumSize(750, 480)
        self.resize(900, 580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        toolbar.addWidget(QLabel("级别:"))
        self._combo_level = QComboBox()
        self._combo_level.addItems(["全部", "DEBUG", "INFO", "WARNING", "ERROR"])
        self._combo_level.setFixedWidth(110)
        self._combo_level.currentIndexChanged.connect(self._on_level_changed)
        toolbar.addWidget(self._combo_level)

        toolbar.addWidget(QLabel("搜索:"))
        self._edit_filter = QLineEdit()
        self._edit_filter.setPlaceholderText("过滤关键词...")
        self._edit_filter.setClearButtonEnabled(True)
        self._edit_filter.setMinimumWidth(140)
        self._edit_filter.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._edit_filter, stretch=1)

        self._chk_auto_scroll = QCheckBox("自动滚动")
        self._chk_auto_scroll.setChecked(True)
        toolbar.addWidget(self._chk_auto_scroll)

        self._btn_pause = QPushButton("暂停")
        self._btn_pause.setMinimumWidth(60)
        self._btn_pause.setFixedHeight(32)
        self._btn_pause.clicked.connect(self._on_toggle_pause)
        toolbar.addWidget(self._btn_pause)

        btn_clear = QPushButton("清空")
        btn_clear.setMinimumWidth(60)
        btn_clear.setFixedHeight(32)
        btn_clear.clicked.connect(self._on_clear)
        toolbar.addWidget(btn_clear)

        btn_export = QPushButton("导出")
        btn_export.setMinimumWidth(60)
        btn_export.setFixedHeight(32)
        btn_export.clicked.connect(self._on_export)
        toolbar.addWidget(btn_export)

        layout.addLayout(toolbar)

        # ── 日志文本区 ──
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setObjectName("debugLogTextEdit")
        self._text_edit.setFont(QFont("Consolas", 10))
        self._text_edit.setMinimumHeight(300)
        layout.addWidget(self._text_edit, stretch=1)

        # ── 状态栏 ──
        status_bar = QHBoxLayout()
        self._lbl_count = QLabel("0 条日志")
        status_bar.addWidget(self._lbl_count)
        status_bar.addStretch()

        self._lbl_status = QLabel("就绪")
        status_bar.addWidget(self._lbl_status)
        layout.addLayout(status_bar)

        # 初始主题
        self.set_theme(True)

    # ── 核心方法 ──

    def append_log(self, message: str, levelno: int):
        """添加一条日志（从 Signal 调用，已在主线程）"""
        if levelno < self._min_level:
            return

        if self._paused:
            return

        # 关键词过滤
        if self._filter_text and self._filter_text.lower() not in message.lower():
            return

        # 颜色
        colors = self._LEVEL_COLORS_LIGHT if not self._is_dark else self._LEVEL_COLORS
        color = colors.get(levelno, "#E8EAED")

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))

        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(message + "\n", fmt)

        self._log_count += 1
        self._lbl_count.setText(f"{self._log_count} 条日志")

        # 自动滚动
        if self._chk_auto_scroll.isChecked():
            self._text_edit.setTextCursor(cursor)
            self._text_edit.ensureCursorVisible()

    def set_theme(self, is_dark: bool):
        """设置主题色"""
        self._is_dark = is_dark
        cls = "debug-log-dark" if is_dark else "debug-log-light"
        self._text_edit.setProperty("class", cls)
        self._text_edit.style().unpolish(self._text_edit)
        self._text_edit.style().polish(self._text_edit)

    # ── 工具栏事件 ──

    def _on_level_changed(self, idx):
        levels = [logging.DEBUG, logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]
        self._min_level = levels[idx] if idx < len(levels) else logging.DEBUG

    def _on_filter_changed(self, text):
        self._filter_text = text.strip()

    def _on_toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._btn_pause.setText("继续")
            self._lbl_status.setText("已暂停")
        else:
            self._btn_pause.setText("暂停")
            self._lbl_status.setText("就绪")

    def _on_clear(self):
        self._text_edit.clear()
        self._log_count = 0
        self._lbl_count.setText("0 条日志")

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志",
            f"feishu_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            "日志文件 (*.log);;文本文件 (*.txt);;所有文件 (*)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._text_edit.toPlainText())
            self._lbl_status.setText(f"已导出: {os.path.basename(path)}")


# ═══ 全局管理器（单实例）═════════════════════════

class DebugLogManager:
    """管理调试日志窗口和 Handler 的生命周期。

    用法:
        mgr = DebugLogManager()
        mgr.enable_debug_window(True)    # 显示调试窗口
        mgr.enable_file_logging(True)    # 启用文件日志
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._window = None
            cls._instance._qt_handler = None
            cls._instance._file_handler = None
            cls._instance._debug_enabled = False
            cls._instance._file_enabled = False
            cls._instance._loggers = [
                "src.services.feishu_service",
                "src.ui.interfaces.feishu_module",
            ]
        return cls._instance

    @property
    def window(self) -> DebugLogWindow:
        """获取或创建调试窗口"""
        if self._window is None:
            self._window = DebugLogWindow()
        return self._window

    @property
    def is_debug_enabled(self) -> bool:
        return self._debug_enabled

    @property
    def is_file_enabled(self) -> bool:
        return self._file_enabled

    def enable_debug_window(self, enabled: bool):
        """启用/禁用调试窗口日志"""
        if enabled and not self._debug_enabled:
            # 创建 Qt Handler
            self._qt_handler = QtLogHandler()
            self._qt_handler.signal_bridge.log_record.connect(self.window.append_log)
            for name in self._loggers:
                logging.getLogger(name).addHandler(self._qt_handler)
                logging.getLogger(name).setLevel(logging.DEBUG)
            self._debug_enabled = True
        elif not enabled and self._debug_enabled:
            # 移除 Handler
            if self._qt_handler:
                for name in self._loggers:
                    logging.getLogger(name).removeHandler(self._qt_handler)
                self._qt_handler.signal_bridge.log_record.disconnect()
                self._qt_handler = None
            self._debug_enabled = False

    def enable_file_logging(self, enabled: bool):
        """启用/禁用文件日志"""
        if enabled and not self._file_enabled:
            self._file_handler = FileLogHandler("data/logs")
            for name in self._loggers:
                logging.getLogger(name).addHandler(self._file_handler)
            self._file_enabled = True
        elif not enabled and self._file_enabled:
            if self._file_handler:
                for name in self._loggers:
                    logging.getLogger(name).removeHandler(self._file_handler)
                self._file_handler = None
            self._file_enabled = False

    def show_window(self):
        """显示调试窗口"""
        w = self.window
        if w.isHidden():
            w.show()
        else:
            w.raise_()
            w.activateWindow()

    def hide_window(self):
        """隐藏调试窗口"""
        if self._window:
            self._window.hide()

    def set_theme(self, is_dark: bool):
        """设置窗口主题"""
        if self._window:
            self._window.set_theme(is_dark)

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def shutdown(self):
        """Shutdown the debug log window and clean up handlers."""
        self.enable_debug_window(False)
        self.enable_file_logging(False)
        if self._window:
            self._window.close()
            self._window = None
