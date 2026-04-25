# -*- coding: utf-8 -*-
"""运费配置接口模块 — 统一卡片风格，动态渲染所有启用的运费模板"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel,
    QPushButton, QDoubleSpinBox, QFormLayout, QDialogButtonBox,
    QDialog, QGroupBox, QScrollArea, QComboBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics

from src.services.shipping_service import ShippingService
from src.ui.interfaces.base import InterfaceModule, ModuleSignals
from src.ui.interfaces.registry import InterfaceRegistry


# ═══ AutoSize Label ═══════════════════════════

class _AutoSizeLabel(QLabel):
    """自动缩放字体以适应可用宽度的 Label"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._base_font_size = 24  # 对应 QSS 中的 rateValue 字体大小
        self._min_font_size = 8

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_font_size()

    def setText(self, text):
        super().setText(text)
        self._adjust_font_size()

    def _adjust_font_size(self):
        text = self.text()
        if not text:
            return
        available_width = self.width() - 4  # 留一点余量
        if available_width <= 0:
            return
        font = self.font()
        for size in range(self._base_font_size, self._min_font_size - 1, -1):
            font.setPointSize(size)
            text_width = QFontMetrics(font).horizontalAdvance(text)
            if text_width <= available_width:
                self.setFont(font)
                return
        # 如果最小字号还是放不下，使用最小字号
        font.setPointSize(self._min_font_size)
        self.setFont(font)


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
    """运费配置对话框 — 动态为每个启用的模板创建配置组"""

    def __init__(self, shipping_svc: ShippingService, templates: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置运费")
        self.setMinimumWidth(360)
        self._svc = shipping_svc
        self._templates = [t for t in templates if t["enabled"]]
        self._spin_boxes: dict[str, tuple[QDoubleSpinBox, QDoubleSpinBox]] = {}
        self._currency_combos: dict[str, QComboBox] = {}
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── 为每个启用的模板创建配置组 ──
        for tpl in self._templates:
            key = tpl["key"]
            display_name = tpl["display_name"]
            currency = tpl["currency"]
            suffix = " ₽" if currency == "RUB" else " ¥"
            suffix_rate = " ₽/L" if currency == "RUB" else " ¥/L"

            grp = QGroupBox(display_name)
            form = QFormLayout(grp)

            spin_base = QDoubleSpinBox()
            spin_base.setRange(0, 99999)
            spin_base.setDecimals(2)
            spin_base.setSuffix(suffix)
            form.addRow("首升费用:", spin_base)

            spin_rate = QDoubleSpinBox()
            spin_rate.setRange(0, 99999)
            spin_rate.setDecimals(2)
            spin_rate.setSuffix(suffix_rate)
            form.addRow("续升单价:", spin_rate)

            combo_currency = QComboBox()
            combo_currency.addItems(["CNY", "RUB"])
            combo_currency.setCurrentText(currency)
            form.addRow("币种:", combo_currency)

            self._spin_boxes[key] = (spin_base, spin_rate)
            self._currency_combos[key] = combo_currency
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
        for tpl in self._templates:
            key = tpl["key"]
            cfg = self._svc.get_config(key)
            spin_base, spin_rate = self._spin_boxes[key]
            spin_base.setValue(cfg["base_fee"])
            spin_rate.setValue(cfg["rate_per_unit"])

    def _on_save(self):
        for tpl in self._templates:
            key = tpl["key"]
            spin_base, spin_rate = self._spin_boxes[key]
            currency = self._currency_combos[key].currentText()
            self._svc.save_config(key, spin_base.value(), spin_rate.value(),
                                  currency=currency)
        self.accept()


# ═══ Widget ═══════════════════════════════════

class _ShippingWidget(QWidget):
    """运费配置卡片内容 — 动态渲染所有启用的运费模板"""

    def __init__(self, signals: ModuleSignals = None):
        super().__init__()
        self._signals = signals
        self._shipping_svc = ShippingService()
        self._build_ui()
        self._refresh_info()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── 动态模板信息区容器 ──
        self._info_container = QVBoxLayout()
        self._info_container.setSpacing(4)
        layout.addLayout(self._info_container)

        layout.addSpacing(4)

        # ── 按钮 ──
        self.btn_config = QPushButton("配置运费")
        self.btn_config.setProperty("class", "btn-primary")
        self.btn_config.setMinimumHeight(36)
        self.btn_config.clicked.connect(self._on_config)
        layout.addWidget(self.btn_config)

    def _refresh_info(self):
        # 清除旧的模板信息区
        while self._info_container.count():
            item = self._info_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # 清理子布局
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        templates = self._shipping_svc.list_templates()

        for tpl in templates:
            if not tpl["enabled"]:
                continue

            key = tpl["key"]
            display_name = tpl["display_name"]
            cfg = tpl["config"]
            currency = tpl["currency"]
            currency_display = tpl["currency_display"]

            # ── 创建信息框 ──
            info_box = QFrame()
            info_box.setObjectName("rateBox")
            inner = QVBoxLayout(info_box)
            inner.setContentsMargins(10, 6, 10, 6)
            inner.setSpacing(1)

            # 第1行: 模板名称（自动缩放）
            lbl_name = _AutoSizeLabel(display_name)
            lbl_name.setObjectName("rateValue")
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inner.addWidget(lbl_name)

            # 第2行: 币种标识
            lbl_currency = QLabel(currency_display)
            lbl_currency.setObjectName("rateHint")
            lbl_currency.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inner.addWidget(lbl_currency)

            # 第3行: 配置摘要（始终显示费率）
            symbol = "₽" if currency == "RUB" else "¥"
            cfg_data = self._shipping_svc.get_config(key)
            summary = f"首升 {symbol}{cfg_data['base_fee']:.0f} · 续升 {symbol}{cfg_data['rate_per_unit']:.0f}/L"

            lbl_summary = QLabel(summary)
            lbl_summary.setObjectName("rateHint")
            lbl_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inner.addWidget(lbl_summary)

            self._info_container.addWidget(info_box)

    def _on_config(self):
        templates = self._shipping_svc.list_templates()
        dlg = _ShippingConfigDialog(self._shipping_svc, templates, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_info()

    def stop_worker(self):
        """No workers needed for config-only module."""
        pass


# 自动注册
InterfaceRegistry.register(ShippingModule)
