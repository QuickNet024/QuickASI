# -*- coding: utf-8 -*-
"""汇率数据接口模块 — 统一卡片风格"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal

from src.models.database import DatabaseManager
from src.services.exchange_rate import ExchangeRateService
from src.config import Config
from src.ui.interfaces.base import InterfaceModule, ModuleSignals
from src.ui.interfaces.registry import InterfaceRegistry
from src.ui.api_settings_dialog import ApiSettingsDialog


# ═══ Worker ═══════════════════════════════════

class ExchangeRateWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, db):
        super().__init__()
        self.db = db

    def run(self):
        try:
            svc = ExchangeRateService(self.db)
            result = svc.fetch_and_save()
            if result:
                self.finished.emit(result)
            else:
                self.error.emit("API返回数据无效")
        except Exception as e:
            self.error.emit(str(e))


# ═══ Module ═══════════════════════════════════

class ExchangeRateModule(InterfaceModule):

    @property
    def module_id(self) -> str:
        return "exchange_rate"

    @property
    def name(self) -> str:
        return "汇率数据"

    @property
    def description(self) -> str:
        return ""

    @property
    def icon_text(self) -> str:
        return "💱"

    def create_widget(self, db, signals: ModuleSignals = None) -> QWidget:
        return _ExchangeRateWidget(db, signals)


class _ExchangeRateWidget(QWidget):
    """汇率数据卡片内容 — 统一 infoBox 风格"""

    def __init__(self, db: DatabaseManager, signals: ModuleSignals = None):
        super().__init__()
        self.db = db
        self._signals = signals
        self._worker = None
        self._build_ui()
        self._load_cached()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── 信息展示框（橙色调，与汇率accent一致）──
        info_box = QFrame()
        info_box.setObjectName("rateBox")
        info_inner = QVBoxLayout(info_box)
        info_inner.setContentsMargins(10, 8, 10, 8)
        info_inner.setSpacing(1)

        lbl_hint = QLabel("今日汇率")
        lbl_hint.setObjectName("rateHint")
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(lbl_hint)

        self.lbl_rate = QLabel("--")
        self.lbl_rate.setObjectName("rateValue")
        self.lbl_rate.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(self.lbl_rate)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("rateHint")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(self.lbl_status)

        layout.addWidget(info_box)
        layout.addSpacing(4)

        # ── 按钮 ──
        self.btn_sync = QPushButton("同步汇率")
        self.btn_sync.setProperty("class", "btn-primary")
        self.btn_sync.setMinimumHeight(36)
        self.btn_sync.clicked.connect(self._on_sync)
        layout.addWidget(self.btn_sync)

        self.btn_settings = QPushButton("API 设置")
        self.btn_settings.setFixedHeight(30)
        self.btn_settings.clicked.connect(self._on_settings)
        layout.addWidget(self.btn_settings)

    def _on_sync(self):
        if self._worker and self._worker.isRunning():
            return
        self.btn_sync.setEnabled(False)
        self.btn_sync.setText("同步中...")
        if self._signals:
            self._signals.sync_started.emit()
        self._worker = ExchangeRateWorker(self.db)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, data):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("同步汇率")
        rate = data["cny_to_rub"]
        ts = str(data.get("updated_at", ""))[:16]
        self.lbl_rate.setText(f"1 CNY = {rate:.4f} RUB")
        self.lbl_status.setText(f"更新: {ts}")
        if self._signals:
            self._signals.rate_updated.emit(rate)

    def _on_error(self, err):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("同步汇率")
        self.lbl_rate.setText("同步失败")
        QMessageBox.warning(self, "汇率同步失败", f"获取汇率失败:\n{err}")

    def _on_settings(self):
        ApiSettingsDialog("汇率 API 设置", [
            ("exchange_rate_api_key", "API Key", Config.EXCHANGE_RATE_API_KEY, True),
            ("exchange_rate_api_url", "API URL",
             "https://v6.exchangerate-api.com/v6/{key}/latest/USD"),
        ], self.db, self).exec()

    def _load_cached(self):
        svc = ExchangeRateService(self.db)
        rate = svc.get_cached_rate()
        if rate and rate.get("cny_to_rub"):
            self.lbl_rate.setText(f"1 CNY = {rate['cny_to_rub']:.4f} RUB")
            ts = str(rate.get("updated_at", ""))[:16]
            self.lbl_status.setText(f"更新: {ts}")


# 自动注册
InterfaceRegistry.register(ExchangeRateModule)
