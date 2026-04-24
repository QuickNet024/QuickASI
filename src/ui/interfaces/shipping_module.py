# -*- coding: utf-8 -*-
"""运费配置接口模块 — 统一卡片风格"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel,
    QPushButton, QDoubleSpinBox, QFormLayout, QDialogButtonBox,
    QDialog, QGroupBox
)
from PySide6.QtCore import Qt

from src.services.shipping_service import ShippingService
from src.ui.interfaces.base import InterfaceModule, ModuleSignals
from src.ui.interfaces.registry import InterfaceRegistry


# ═══ Module ═══════════════════════════════════

class ShippingModule(InterfaceModule):

    @property
    def module_id(self) -> str:
        return "shipping"

    @property
    def name(self) -> str:
        return "运费配置"

    @property
    def description(self) -> str:
        return ""

    @property
    def icon_text(self) -> str:
        return "📦"

    def create_widget(self, db, signals: ModuleSignals = None) -> QWidget:
        return _ShippingWidget(signals)


# ═══ Config Dialog ════════════════════════════

class _ShippingConfigDialog(QDialog):
    """运费配置对话框"""

    def __init__(self, shipping_svc: ShippingService, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置运费")
        self.setMinimumWidth(320)
        self._svc = shipping_svc
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── WB跨境 本土仓发货 ──
        grp = QGroupBox("WB跨境 · 本土仓发货")
        form = QFormLayout(grp)
        self._spin_base = QDoubleSpinBox()
        self._spin_base.setRange(0, 99999)
        self._spin_base.setDecimals(2)
        self._spin_base.setSuffix(" ¥")
        form.addRow("首升费用:", self._spin_base)

        self._spin_rate = QDoubleSpinBox()
        self._spin_rate.setRange(0, 99999)
        self._spin_rate.setDecimals(2)
        self._spin_rate.setSuffix(" ¥/L")
        form.addRow("续升单价:", self._spin_rate)
        layout.addWidget(grp)

        # ── 按钮 ──
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _load_config(self):
        cfg = self._svc.get_config("wb_cross_border")
        self._spin_base.setValue(cfg["base_fee"])
        self._spin_rate.setValue(cfg["rate_per_unit"])

    def _on_save(self):
        self._svc.save_config(
            "wb_cross_border",
            self._spin_base.value(),
            self._spin_rate.value(),
        )
        self.accept()


# ═══ Widget ═══════════════════════════════════

class _ShippingWidget(QWidget):
    """运费配置卡片内容 — 统一 infoBox 风格"""

    def __init__(self, signals: ModuleSignals = None):
        super().__init__()
        self._signals = signals
        self._shipping_svc = ShippingService()
        self._build_ui()
        self._refresh_info()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── 信息展示框 ──
        info_box = QFrame()
        info_box.setObjectName("rateBox")
        info_inner = QVBoxLayout(info_box)
        info_inner.setContentsMargins(10, 8, 10, 8)
        info_inner.setSpacing(1)

        lbl_hint = QLabel("运费模式")
        lbl_hint.setObjectName("rateHint")
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(lbl_hint)

        self.lbl_mode = QLabel("--")
        self.lbl_mode.setObjectName("rateValue")
        self.lbl_mode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(self.lbl_mode)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("rateHint")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_inner.addWidget(self.lbl_status)

        layout.addWidget(info_box)
        layout.addSpacing(4)

        # ── 按钮 ──
        self.btn_config = QPushButton("配置运费")
        self.btn_config.setProperty("class", "btn-primary")
        self.btn_config.setMinimumHeight(36)
        self.btn_config.clicked.connect(self._on_config)
        layout.addWidget(self.btn_config)

    def _refresh_info(self):
        cfg = self._shipping_svc.get_config("wb_cross_border")

        # Show current mode concisely
        self.lbl_mode.setText("WB跨境 · 本土仓")

        # Check if config differs from defaults
        if (cfg["base_fee"] != 8.0 or cfg["rate_per_unit"] != 2.0):
            self.lbl_status.setText(f"首升 ¥{cfg['base_fee']:.0f} · 续升 ¥{cfg['rate_per_unit']:.0f}/L")
        else:
            self.lbl_status.setText("使用默认配置")

    def _on_config(self):
        dlg = _ShippingConfigDialog(self._shipping_svc, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_info()

    def stop_worker(self):
        """No workers needed for config-only module."""
        pass


# 自动注册
InterfaceRegistry.register(ShippingModule)
