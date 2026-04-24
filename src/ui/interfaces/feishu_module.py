# -*- coding: utf-8 -*-
"""飞书数据接口模块 — 统一卡片风格"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QMessageBox, QProgressBar,
    QDialog, QDialogButtonBox, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal

from src.models.database import DatabaseManager
from src.services.feishu_service import FeishuService, SyncAbortException
from src.config import Config
from src.ui.interfaces.base import InterfaceModule, ModuleSignals
from src.ui.interfaces.registry import InterfaceRegistry
from src.ui.api_settings_dialog import ApiSettingsDialog
from src.ui.assets.icons import get_util_icon


# ═══ Worker ═══════════════════════════════════

class FeishuSyncWorker(QThread):
    finished = Signal(int, list)
    error = Signal(str)

    def __init__(self, db, sync_images=False):
        super().__init__()
        # db is app_db; create module-specific DB for product operations
        self._feishu_db = DatabaseManager(Config.DB_FEISHU_PATH, init_tables=["products", "app_config"])
        self.sync_images = sync_images

    def run(self):
        try:
            svc = FeishuService(self._feishu_db)
            count, sheets = svc.sync_all_products(sync_images=self.sync_images)
            if not self.isInterruptionRequested():
                self.finished.emit(count, sheets)
        except SyncAbortException as e:
            if not self.isInterruptionRequested():
                self.error.emit(f"同步已自动停止: {e}")
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error.emit(str(e))


# ═══ 同步选项对话框 ═══════════════════════════

class _SyncOptionsDialog(QDialog):
    """同步数据选项 — 询问是否同步图片"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("同步选项")
        self.setMinimumWidth(300)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        hint = QLabel("准备从飞书同步产品数据")
        layout.addWidget(hint)

        self._check_images = QCheckBox("同步产品图片（首次较慢）")
        layout.addWidget(self._check_images)

        layout.addSpacing(8)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def should_sync_images(self) -> bool:
        return self._check_images.isChecked()


# ═══ Module ═══════════════════════════════════

class FeishuModule(InterfaceModule):

    @property
    def module_id(self) -> str:
        return "feishu"

    @property
    def name(self) -> str:
        return "飞书数据"

    @property
    def description(self) -> str:
        return ""

    @property
    def icon_text(self) -> str:
        return ""

    def create_widget(self, db, signals: ModuleSignals = None) -> QWidget:
        return _FeishuWidget(db, signals)


class _FeishuWidget(QWidget):
    """飞书数据卡片内容 — 统一 infoBox 风格"""

    def __init__(self, db: DatabaseManager, signals: ModuleSignals = None):
        super().__init__()
        # db is app_db for registry; create module-specific DB
        self.db = DatabaseManager(Config.DB_FEISHU_PATH, init_tables=["products", "app_config"])
        self._signals = signals
        self._worker = None
        self._build_ui()
        self._refresh_status()
        self._restore_debug_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── 信息展示框（统一 rateBox 风格）──
        info_box = QFrame()
        info_box.setObjectName("feishuInfoBox")
        info_inner = QVBoxLayout(info_box)
        info_inner.setContentsMargins(10, 8, 10, 8)
        info_inner.setSpacing(1)

        lbl_hint = QLabel("缓存数据")
        lbl_hint.setObjectName("rateHint")
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(lbl_hint)

        self.lbl_count = QLabel("--")
        self.lbl_count.setObjectName("rateValue")
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(self.lbl_count)

        self.lbl_sync_time = QLabel("")
        self.lbl_sync_time.setObjectName("rateHint")
        self.lbl_sync_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(self.lbl_sync_time)

        layout.addWidget(info_box)
        layout.addSpacing(4)

        # ── 按钮 ──
        self.btn_sync = QPushButton("同步数据")
        self.btn_sync.setProperty("class", "btn-primary")
        self.btn_sync.setMinimumHeight(36)
        self.btn_sync.clicked.connect(self._on_sync)
        layout.addWidget(self.btn_sync)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_settings = QPushButton("API 设置")
        self.btn_settings.setFixedHeight(30)
        self.btn_settings.clicked.connect(self._on_settings)
        btn_row.addWidget(self.btn_settings)

        self.btn_advanced = QPushButton(" 高级设置")
        self.btn_advanced.setFixedHeight(30)
        self.btn_advanced.setIcon(get_util_icon("settings", 14))
        self.btn_advanced.clicked.connect(self._on_advanced)
        btn_row.addWidget(self.btn_advanced)

        layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setMaximumHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

    def _on_sync(self):
        # 如果正在同步 → 取消
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.quit()
            self._worker.wait(3000)
            self._on_cancel()
            return

        dlg = _SyncOptionsDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        sync_images = dlg.should_sync_images()
        self.btn_sync.setText("取消同步")
        self.btn_sync.setProperty("class", "btn-danger")
        self.btn_sync.style().unpolish(self.btn_sync)
        self.btn_sync.style().polish(self.btn_sync)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        if self._signals:
            self._signals.sync_started.emit()
        self._worker = FeishuSyncWorker(self.db, sync_images)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _reset_sync_button(self):
        """恢复同步按钮为初始状态"""
        self.btn_sync.setText("同步数据")
        self.btn_sync.setProperty("class", "btn-primary")
        self.btn_sync.style().unpolish(self.btn_sync)
        self.btn_sync.style().polish(self.btn_sync)
        self.progress.setVisible(False)

    def _on_done(self, count, sheets):
        self._reset_sync_button()
        self._refresh_status()
        if self._signals:
            self._signals.sync_finished.emit()
            self._signals.stats_changed.emit()

    def _on_error(self, err):
        self._reset_sync_button()
        self.lbl_count.setText("同步失败")
        QMessageBox.warning(self, "飞书同步失败", err)

    def _on_cancel(self):
        """用户手动取消同步"""
        self._reset_sync_button()
        self.lbl_count.setText("已取消")
        if self._signals:
            self._signals.sync_finished.emit()

    def _on_settings(self):
        ApiSettingsDialog("飞书 API 设置", [
            ("feishu_app_id", "App ID", Config.FEISHU_APP_ID),
            ("feishu_app_secret", "App Secret", Config.FEISHU_APP_SECRET, True),
            ("feishu_sheet_token", "表格 Token", Config.FEISHU_SPREADSHEET_TOKEN),
        ], self.db, self).exec()

    def _on_advanced(self):
        from src.ui.feishu_advanced_dialog import FeishuAdvancedDialog
        dlg = FeishuAdvancedDialog(self.db, self)
        dlg.exec()

    def _refresh_status(self):
        count = self.db.get_product_count()
        self.lbl_count.setText(f"{count} 条")
        last_time = self.db.get_last_product_sync_time()
        if last_time:
            self.lbl_sync_time.setText(f"上次同步: {last_time}")
        else:
            self.lbl_sync_time.setText("暂未同步")

    def _restore_debug_settings(self):
        """应用启动时，从 DB 恢复调试日志设置"""
        from src.ui.debug_log_window import DebugLogManager
        mgr = DebugLogManager()
        if self.db.get_config("debug_window_enabled", "0") == "1":
            mgr.enable_debug_window(True)
        if self.db.get_config("debug_file_enabled", "0") == "1":
            mgr.enable_file_logging(True)

    def stop_worker(self):
        """Stop the worker thread gracefully."""
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.quit()
            self._worker.wait(3000)
            if self._worker.isRunning():
                self._worker.terminate()
                self._worker.wait(1000)


# 自动注册
InterfaceRegistry.register(FeishuModule)
