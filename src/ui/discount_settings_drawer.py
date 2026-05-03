# -*- coding: utf-8 -*-
"""折扣配置抽屉 — 右侧覆盖式滑出面板。

以 overlay 模式从右侧滑入，覆盖在表格上方，
包含店铺/佣金、汇率、计算目标、导出策略、操作按钮 5 个配置组。

用法::

    drawer = DiscountSettingsDrawer(parent=self)
    drawer.applied.connect(self._on_drawer_applied)
    drawer.saved_as_default.connect(self._on_drawer_saved)
    drawer.set_values(shop_type="wb_cross_border", ...)
    drawer.open()
    values = drawer.get_values()
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QPoint, QEvent
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QWidget,
)

from src.ui.table_base import ThemeColors


class DiscountSettingsDrawer(QFrame):
    """右侧覆盖式配置抽屉 — 滑入/滑出动画 + 半透明遮罩。

    Signals:
        applied: 用户点击"应用"按钮后触发
        saved_as_default: 用户点击"保存为默认配置"后触发
    """

    applied = Signal()
    saved_as_default = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsDrawer")
        self.setFixedWidth(320)
        self.setVisible(False)

        self._anim: QPropertyAnimation | None = None
        self._backdrop: QFrame | None = None

        self._init_backdrop()
        self._init_ui()
        self._update_theme_colors()

    # ── Backdrop 遮罩 ────────────────────────────────────

    def _init_backdrop(self):
        """Create semi-transparent backdrop filling parent, click-to-close."""
        parent = self.parent()
        if parent is None:
            return
        self._backdrop = QFrame(parent)
        self._backdrop.setObjectName("drawerBackdrop")
        self._backdrop.setVisible(False)
        self._backdrop.installEventFilter(self)
        parent.installEventFilter(self)

    def eventFilter(self, obj, event):
        # Click backdrop → close drawer
        if obj is self._backdrop and event.type() == QEvent.Type.MouseButtonPress:
            self.close()
            return True
        # Parent resize → update backdrop & drawer geometry
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self._on_parent_resized(event)
            return False
        return super().eventFilter(obj, event)

    def _on_parent_resized(self, event):
        """Keep backdrop and drawer sized correctly when parent resizes."""
        if self._backdrop is None:
            return
        pw = event.size().width()
        ph = event.size().height()
        if self._backdrop.isVisible():
            self._backdrop.resize(pw, ph)
        if self.isVisible():
            right_margin = pw - self.x()  # distance from right edge
            self.setGeometry(pw - right_margin, 0, 320, ph)

    # ── 主题配色 ─────────────────────────────────────────

    def _update_theme_colors(self):
        """Read ThemeColors and apply light/dark QSS to drawer + backdrop."""
        is_dark = ThemeColors.get_theme() == "dark"

        # Backdrop
        backdrop_color = "rgba(0, 0, 0, 0.40)" if is_dark else "rgba(0, 0, 0, 0.30)"
        if self._backdrop is not None:
            self._backdrop.setStyleSheet(
                f"QFrame#drawerBackdrop {{ background: {backdrop_color}; }}"
            )

        # Drawer colours
        bg = "#2D2D2D" if is_dark else "#FFFFFF"
        border = "#444444" if is_dark else "#E0E0E0"
        label_color = "#9AA0A6" if is_dark else "#5F6368"
        text_color = "#E0E0E0" if is_dark else "#1C1B1F"
        hover_bg = "#3A3A3A" if is_dark else "#F0F0F0"

        self.setStyleSheet(f"""
            QWidget#settingsDrawer {{
                background: {bg};
                border-left: 1px solid {border};
            }}
            QWidget#settingsDrawer QGroupBox {{
                font-weight: 600;
                font-size: 12px;
                color: {text_color};
                border: 1px solid {border};
                border-radius: 8px;
                margin-top: 12px;
                padding: 18px 12px 12px 12px;
            }}
            QWidget#settingsDrawer QGroupBox::title {{
                subcontrol-origin: border;
                subcontrol-position: top left;
                padding: 2px 8px;
                color: {text_color};
            }}
            QWidget#settingsDrawer QLabel#fieldLabel {{
                color: {label_color};
            }}
            QWidget#settingsDrawer QPushButton#drawerCloseBtn {{
                background: transparent;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                color: {text_color};
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }}
            QWidget#settingsDrawer QPushButton#drawerCloseBtn:hover {{
                background: {hover_bg};
            }}
        """)

    def refresh_theme(self, theme: str):
        """Re-apply theme colors after theme switch."""
        self._update_theme_colors()

    # ── UI 构建 ─────────────────────────────────────────
 
    def _init_ui(self):
        """Build header + scrollable 5-group form."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = self._build_header()
        layout.addWidget(header)

        # ── Scrollable content ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("drawerScroll")
        # Ensure viewport is transparent so drawer background shows through
        scroll.viewport().setAutoFillBackground(False)

        content = QWidget()
        content.setObjectName("drawerContent")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(12, 4, 12, 12)
        cl.setSpacing(4)

        cl.addWidget(self._build_group_shop())
        cl.addWidget(self._build_group_exchange_rate())
        cl.addWidget(self._build_group_target())
        cl.addWidget(self._build_group_strategy())
        cl.addWidget(self._build_group_export_filter())
        cl.addWidget(self._build_group_actions())
        cl.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

    def _build_header(self) -> QWidget:
        """Drawer title bar with close button."""
        header = QWidget()
        header.setObjectName("drawerHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 12, 12, 8)
        hl.setSpacing(8)

        title = QLabel("配置参数")
        title.setObjectName("drawerTitle")
        title_font = title.font()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title.setFont(title_font)
        hl.addWidget(title)
        hl.addStretch()

        btn = QPushButton("✕")
        btn.setObjectName("drawerCloseBtn")
        btn.clicked.connect(self.close)
        hl.addWidget(btn)

        return header

    # -- 配置组 1: 店铺与佣金 ------------------------------------------------

    def _build_group_shop(self) -> QGroupBox:
        """店铺类型, 佣金表, 默认佣金率, 佣金类目来源."""
        group = QGroupBox("店铺与佣金")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        layout.addWidget(self._make_label("店铺类型"))
        self._combo_shop = QComboBox()
        self._combo_shop.addItem("WB 跨境 · CNY", "wb_cross_border")
        self._combo_shop.addItem("WB 本土 · RUB", "wb_local")
        layout.addWidget(self._combo_shop)

        layout.addWidget(self._make_label("佣金表"))
        self._combo_commission = QComboBox()
        layout.addWidget(self._combo_commission)

        layout.addWidget(self._make_label("默认佣金率"))
        self._spin_default_commission = QDoubleSpinBox()
        self._spin_default_commission.setRange(0, 100)
        self._spin_default_commission.setSuffix(" %")
        self._spin_default_commission.setValue(30.0)
        layout.addWidget(self._spin_default_commission)

        layout.addWidget(self._make_label("佣金类目来源"))
        self._combo_category_source = QComboBox()
        self._combo_category_source.addItem("飞书产品类目", "feishu")
        self._combo_category_source.addItem("Excel表格类目", "excel")
        layout.addWidget(self._combo_category_source)

        return group

    # -- 配置组 2: 汇率 ----------------------------------------------------

    def _build_group_exchange_rate(self) -> QGroupBox:
        """实时汇率/手动指定 radio + 手动汇率 spinbox."""
        group = QGroupBox("汇率")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self._rate_group = QButtonGroup(self)
        self._rb_realtime = QRadioButton("实时汇率")
        self._rb_manual = QRadioButton("手动指定")
        self._rate_group.addButton(self._rb_realtime)
        self._rate_group.addButton(self._rb_manual)
        self._rb_realtime.setChecked(True)
        layout.addWidget(self._rb_realtime)
        layout.addWidget(self._rb_manual)

        self._spin_rate = QDoubleSpinBox()
        self._spin_rate.setRange(0.01, 100.0)
        self._spin_rate.setDecimals(4)
        self._spin_rate.setValue(12.0)
        self._spin_rate.setEnabled(False)  # disabled when realtime selected
        layout.addWidget(self._spin_rate)

        self._rb_realtime.toggled.connect(self._toggle_rate_spin)
        return group

    # -- 配置组 3: 计算目标 -------------------------------------------------

    def _build_group_target(self) -> QGroupBox:
        """利润率/固定利润 radio + target spinbox (自适应单位/范围)."""
        group = QGroupBox("计算目标")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self._calc_group = QButtonGroup(self)
        self._rb_profit_rate = QRadioButton("按利润率")
        self._rb_fixed_profit = QRadioButton("按固定利润")
        self._calc_group.addButton(self._rb_profit_rate)
        self._calc_group.addButton(self._rb_fixed_profit)
        self._rb_profit_rate.setChecked(True)
        layout.addWidget(self._rb_profit_rate)
        layout.addWidget(self._rb_fixed_profit)

        self._spin_target = QDoubleSpinBox()
        self._spin_target.setRange(0, 100)
        self._spin_target.setSuffix(" %")
        self._spin_target.setValue(10.0)
        self._spin_target.setDecimals(2)
        layout.addWidget(self._spin_target)

        self._rb_profit_rate.toggled.connect(self._toggle_target_spin)
        return group

    # -- 配置组 4: 导出策略 ------------------------------------------------

    def _build_group_strategy(self) -> QGroupBox:
        """折扣优先 / 价格优先 / 价格+折扣 / 保持折扣调价 / 折扣归零调价."""
        group = QGroupBox("导出策略")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self._combo_strategy = QComboBox()
        self._combo_strategy.addItem("折扣优先", "discount_only")
        self._combo_strategy.addItem("保持折扣调价", "keep_discount")
        self._combo_strategy.addItem("折扣归零调价", "zero_discount")
        layout.addWidget(self._combo_strategy)

        return group

    # -- 配置组 4b: 导出筛选 ------------------------------------------------

    def _build_group_export_filter(self) -> QGroupBox:
        """按利润值/利润率 radio + 阈值 spinbox，仅导出低于阈值的商品."""
        group = QGroupBox("导出筛选")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self._export_filter_group = QButtonGroup(self)
        self._radio_profit_value = QRadioButton("按利润值")
        self._radio_profit_rate = QRadioButton("按利润率")
        self._export_filter_group.addButton(self._radio_profit_value)
        self._export_filter_group.addButton(self._radio_profit_rate)
        self._radio_profit_value.setChecked(True)
        layout.addWidget(self._radio_profit_value)
        layout.addWidget(self._radio_profit_rate)

        self._spin_export_threshold = QDoubleSpinBox()
        self._spin_export_threshold.setRange(0, 99999)
        self._spin_export_threshold.setSuffix(" 元")
        self._spin_export_threshold.setDecimals(2)
        self._spin_export_threshold.setValue(0)
        layout.addWidget(self._spin_export_threshold)

        layout.addWidget(QLabel("仅导出低于此阈值的商品"))

        self._radio_profit_value.toggled.connect(self._toggle_export_threshold_spin)
        return group

    # -- 配置组 5: 操作按钮 ------------------------------------------------

    def _build_group_actions(self) -> QGroupBox:
        """应用 & 保存为默认配置."""
        group = QGroupBox("操作")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self._btn_apply = QPushButton("✓ 应用并保存")
        self._btn_apply.setProperty("class", "btn-primary")
        self._btn_apply.setFixedHeight(36)
        self._btn_apply.clicked.connect(self._on_apply_save)
        layout.addWidget(self._btn_apply)

        return group

    # ── 内部辅助 ─────────────────────────────────────────

    @staticmethod
    def _make_label(text: str) -> QLabel:
        """Create a field label styled via global ``QLabel#fieldLabel`` QSS."""
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _toggle_rate_spin(self, _checked: bool):
        """Enable manual spinbox only when '手动指定' is active."""
        self._spin_rate.setEnabled(self._rb_manual.isChecked())

    def _toggle_target_spin(self, _checked: bool):
        """Swap target spinbox range/suffix for profit-rate vs fixed-profit."""
        if self._rb_profit_rate.isChecked():
            self._spin_target.setRange(0, 100)
            self._spin_target.setSuffix(" %")
            self._spin_target.setDecimals(2)
            self._spin_target.setValue(10.0)
        else:
            self._spin_target.setRange(0, 100000)
            self._spin_target.setSuffix(" ¥")
            self._spin_target.setDecimals(2)
            self._spin_target.setValue(20.0)

    def _toggle_export_threshold_spin(self, _checked: bool):
        """Swap export threshold spinbox range/suffix for value vs rate."""
        if self._radio_profit_value.isChecked():
            self._spin_export_threshold.setRange(0, 99999)
            self._spin_export_threshold.setSuffix(" 元")
            self._spin_export_threshold.setDecimals(2)
            self._spin_export_threshold.setValue(0)
        else:
            self._spin_export_threshold.setRange(0, 100)
            self._spin_export_threshold.setSuffix(" %")
            self._spin_export_threshold.setDecimals(1)
            self._spin_export_threshold.setValue(10.0)

    def _on_apply(self):
        self.applied.emit()

    def _on_save_default(self):
        self.saved_as_default.emit()

    def _on_apply_save(self):
        """Apply settings then save as defaults."""
        self._on_apply()
        self._on_save_default()

    # ── 动画 ─────────────────────────────────────────────

    def open(self):
        """Animate drawer sliding in from the right (250ms, OutCubic)."""
        self._cleanup_anim()

        parent = self.parent()
        if parent is None or self._backdrop is None:
            return

        pw = parent.width()
        ph = parent.height()

        # Backdrop covers parent
        self._backdrop.resize(pw, ph)
        self._backdrop.show()
        self._backdrop.raise_()

        # Drawer positioned off-screen right
        self.setGeometry(pw, 0, 320, ph)
        self.show()
        self.raise_()

        # Slide in
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(250)
        self._anim.setStartValue(QPoint(pw, 0))
        self._anim.setEndValue(QPoint(pw - 320, 0))
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def close(self):
        """Animate drawer sliding out to the right (250ms, OutCubic)."""
        self._cleanup_anim()

        parent = self.parent()
        if parent is None:
            return

        pw = parent.width()

        # Already closed
        if not self.isVisible() or self.x() >= pw:
            return

        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(250)
        self._anim.setStartValue(QPoint(self.x(), 0))
        self._anim.setEndValue(QPoint(pw, 0))
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_close_finished)
        self._anim.start()

    def _cleanup_anim(self):
        """Safely stop and disconnect the current animation."""
        if self._anim is None:
            return
        try:
            if self._anim.receivers(self._anim.finished) > 0:
                self._anim.finished.disconnect(self._on_close_finished)
        except (TypeError, RuntimeError):
            pass
        self._anim.stop()
        self._anim = None

    def _on_close_finished(self):
        """Hide drawer and backdrop after close animation completes."""
        self._cleanup_anim()
        self.setVisible(False)
        if self._backdrop is not None:
            self._backdrop.setVisible(False)

    # ── 公共 API ─────────────────────────────────────────

    def set_values(
        self,
        shop_type=None,
        commission_table=None,
        default_commission=None,
        category_source=None,
        exchange_rate_mode=None,
        exchange_rate_value=None,
        calc_mode=None,
        target_value=None,
        strategy=None,
        export_filter_mode=None,
        export_filter_threshold=None,
    ):
        """Pre-populate all controls. Pass ``None`` to leave a field unchanged."""
        if shop_type is not None:
            self._set_combo_by_data(self._combo_shop, shop_type)
        if commission_table is not None:
            self._set_combo_by_data(self._combo_commission, commission_table)
        if default_commission is not None:
            self._spin_default_commission.setValue(default_commission)
        if category_source is not None:
            self._set_combo_by_data(self._combo_category_source, category_source)
        if exchange_rate_mode is not None:
            if exchange_rate_mode == "realtime":
                self._rb_realtime.setChecked(True)
            else:
                self._rb_manual.setChecked(True)
        if exchange_rate_value is not None:
            self._spin_rate.setValue(exchange_rate_value)
        if calc_mode is not None:
            if calc_mode == "profit_rate":
                self._rb_profit_rate.setChecked(True)
            else:
                self._rb_fixed_profit.setChecked(True)
        if target_value is not None:
            self._spin_target.setValue(target_value)
        if strategy is not None:
            self._set_combo_by_data(self._combo_strategy, strategy)
        if export_filter_mode is not None:
            if export_filter_mode == "profit_rate":
                self._radio_profit_rate.setChecked(True)
            else:
                self._radio_profit_value.setChecked(True)
        if export_filter_threshold is not None:
            self._spin_export_threshold.setValue(export_filter_threshold)

    def get_values(self) -> dict:
        """Return a dict of all current configuration values."""
        return {
            "shop_type": self._combo_shop.currentData(),
            "commission_table": self._combo_commission.currentData(),
            "default_commission": self._spin_default_commission.value(),
            "category_source": self._combo_category_source.currentData(),
            "exchange_rate_mode": "realtime" if self._rb_realtime.isChecked() else "manual",
            "exchange_rate_value": self._spin_rate.value(),
            "calc_mode": "profit_rate" if self._rb_profit_rate.isChecked() else "fixed_profit",
            "target_value": self._spin_target.value(),
            "strategy": self._combo_strategy.currentData(),
            "export_filter_mode": "profit_rate" if self._radio_profit_rate.isChecked() else "profit_value",
            "export_filter_threshold": self._spin_export_threshold.value(),
        }

    def load_commission_tables(self, tables: list[tuple[str, str]]):
        """Populate the commission table combobox.

        Args:
            tables: List of ``(display_label, data_value)`` pairs.
                    Falls back to "WB 跨境 · 默认" if list is empty.
        """
        self._combo_commission.blockSignals(True)
        self._combo_commission.clear()
        for label, data in tables:
            self._combo_commission.addItem(label, data)
        if self._combo_commission.count() == 0:
            self._combo_commission.addItem("WB 跨境 · 默认", "commission_wb_cross_border")
        self._combo_commission.blockSignals(False)

    # ── 内部工具 ─────────────────────────────────────────

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value):
        """Set QComboBox current index by ``itemData()`` match."""
        if value is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
