# -*- coding: utf-8 -*-
"""匹配设置对话框 — 运费配置选择"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout,
    QLabel, QRadioButton, QButtonGroup,
    QGroupBox, QDialogButtonBox
)

# shop_type → commission table name mapping
_SHOP_TYPE_COMMISSION = {
    "wb_cross_border": "commission_wb_cross_border",
    "wb_local": "commission_wb_local",
}


class MatchSettingsDialog(QDialog):
    """匹配前选择运费配置 — 动态显示 ShippingService 中的所有可用配置"""

    def __init__(self, parent=None, last_shop_type="wb_cross_border"):
        super().__init__(parent)
        self.setWindowTitle("匹配设置")
        self.setMinimumWidth(420)
        self._radio_buttons = {}  # shop_type → QRadioButton
        self._templates = []      # cached template list
        self._build_ui(last_shop_type)

    def _build_ui(self, last_shop_type):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # ── 运费配置选择 ──
        config_group = QGroupBox("运费配置")
        config_layout = QVBoxLayout(config_group)

        # Load templates from ShippingService
        try:
            from src.services.shipping_service import ShippingService
            svc = ShippingService()
            self._templates = svc.list_templates()
        except Exception:
            self._templates = [{
                "key": "wb_cross_border",
                "display_name": "WB平台-跨境-FBS(国内发货)",
                "config": {"base_fee": 8.0, "rate_per_unit": 2.0},
                "currency": "CNY",
                "currency_display": "CNY (¥)",
                "enabled": True,
            }]

        grp = QButtonGroup(self)
        for tpl in self._templates:
            key = tpl["key"]
            display_name = tpl["display_name"]
            cfg = tpl["config"]
            currency_symbol = "₽" if tpl["currency"] == "RUB" else "¥"
            enabled = tpl["enabled"]

            rb = QRadioButton(display_name)
            rb.setEnabled(enabled)

            # Config detail label
            if enabled and cfg.get("base_fee", 0) > 0:
                detail = f"    首升 {currency_symbol}{cfg['base_fee']:.0f} + 续升 {currency_symbol}{cfg['rate_per_unit']:.0f}/L"
            elif not enabled:
                detail = "    (暂未开放)"
            else:
                detail = ""
            lbl = QLabel(detail)

            # Pre-select the last used shop_type
            if key == last_shop_type and enabled:
                rb.setChecked(True)

            grp.addButton(rb)
            self._radio_buttons[key] = rb

            config_layout.addWidget(rb)
            config_layout.addWidget(lbl)

        # If nothing was checked, check first enabled one
        if not any(rb.isChecked() for rb in self._radio_buttons.values()):
            for key, rb in self._radio_buttons.items():
                if rb.isEnabled():
                    rb.setChecked(True)
                    break

        layout.addWidget(config_group)

        # ── 确认/取消按钮 ──
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("开始匹配")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_shop_type(self) -> str:
        """Return the selected shop_type key."""
        for key, rb in self._radio_buttons.items():
            if rb.isChecked():
                return key
        return "wb_cross_border"  # default

    def get_commission_table(self) -> str:
        """Return the commission table name for the selected shop_type."""
        shop_type = self.get_shop_type()
        return _SHOP_TYPE_COMMISSION.get(shop_type, "commission_wb_cross_border")
