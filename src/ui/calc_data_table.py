# -*- coding: utf-8 -*-
"""计算数据表格组件 — 显示详细计算明细（运费、盈亏平衡、盈亏额等）"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton, QHeaderView

from src.ui.table_base import (
    BaseTableModel,
    BaseTableView,
    ThemeColors,
)

# ---------------------------------------------------------------------------
# CalcDataModel
# ---------------------------------------------------------------------------

_COLUMNS = [
    ("row_number", "行号", 50),
    ("seller_sku", "卖家货号", 150),
    ("current_price", "当前价格", 80),
    ("current_discount", "当前折扣", 70),
    ("discounted_price", "折后价格", 80),
    ("product_cost", "产品成本", 80),
    ("shipping_fee", "运费", 70),
    ("cbase", "基础成本", 80),
    ("crisk", "风险成本", 80),
    ("r_total", "综合费率", 70),
    ("total_fixed", "总固定成本", 80),
    ("breakeven", "盈亏平衡点", 90),
    ("profit", "盈亏额", 80),
    ("current_profit_rate", "当前利润率", 80),
    ("max_discount", "保本折扣", 70),
    ("target_discount", "目标折扣", 70),
    ("min_price", "保本价格", 80),
    ("target_price", "目标价格", 80),
    ("target_new_price", "建议新原价", 90),
    ("_view", "操作", 56),
]

_PCT_KEYS = {"current_discount", "max_discount", "target_discount", "current_profit_rate"}
_MONEY_KEYS = {
    "current_price", "discounted_price", "product_cost",
    "shipping_fee", "cbase", "crisk", "total_fixed",
    "breakeven", "profit", "min_price", "target_price", "target_new_price",
}


class CalcDataModel(BaseTableModel):
    """计算数据表格模型。"""

    COLUMNS = _COLUMNS

    def __init__(self, parent=None):
        super().__init__(self.COLUMNS, parent)

    # -- 格式化 -------------------------------------------------------------

    def _format_value(self, row: int, col: int) -> str:
        key = self._col_key(col)
        val = self._col_value(self._data[row], col) if row < len(self._data) else None

        if key == "_view":
            return ""

        if key == "r_total":
            try:
                return f"{float(val) * 100:.2f}%"
            except (ValueError, TypeError):
                return str(val) if val else "-"

        if key in _PCT_KEYS:
            try:
                return f"{int(float(val))}%"
            except (ValueError, TypeError):
                return str(val) if val else "-"

        if key in _MONEY_KEYS:
            try:
                return f"{float(val):.2f}"
            except (ValueError, TypeError):
                return str(val) if val else "-"

        return str(val) if val is not None and val != "" else "-"

    # -- data() 覆写 (ForegroundRole for profit) ----------------------------

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        col = index.column()
        key = self._col_key(col)

        # _view 列完全交给 setIndexWidget
        if key == "_view":
            return None

        # 前景色: profit / current_profit_rate 列正绿负红
        if role == Qt.ItemDataRole.ForegroundRole and key in ("profit", "current_profit_rate"):
            val = self._col_value(self._data[index.row()], col) if index.row() < len(self._data) else None
            if isinstance(val, (int, float)):
                if val > 0:
                    return ThemeColors.profit_fg()
                elif val < 0:
                    return ThemeColors.loss_fg()
            return None

        return super().data(index, role)


# ---------------------------------------------------------------------------
# CalcDataTable
# ---------------------------------------------------------------------------

class CalcDataTable(BaseTableView):
    """计算数据表格视图 — 使用 QTableView + CalcDataModel。"""

    MATCH_COLUMN_KEYS = {"product_cost", "shipping_fee"}
    CALC_COLUMN_KEYS = {
        "breakeven", "profit", "max_discount", "target_discount",
        "min_price", "target_price", "target_new_price",
    }

    view_clicked = Signal(int)

    def __init__(self, parent=None):
        model = CalcDataModel()
        super().__init__(model, parent)
        self.setObjectName("calcTable")
        self._filter_skip_keys = {"_view"}
        self._init_view_column()

    # -- 操作列固定宽度 -------------------------------------------------------

    def _init_view_column(self):
        """Set _view column as fixed width."""
        view_col = len(self._model.COLUMNS) - 1
        header = self.horizontalHeader()
        header.setSectionResizeMode(view_col, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(view_col, 56)

    def _auto_fit_columns(self):
        """Override: auto-fit all columns except _view which stays fixed."""
        super()._auto_fit_columns()
        self._init_view_column()

    def _rebuild_view_buttons(self):
        """清除并重建所有可见行的查看按钮。"""
        view_col = len(self._model.COLUMNS) - 1  # _view 最后一列 (index 17)

        # 清除已有按钮
        for row in range(self._proxy.rowCount()):
            idx = self._proxy.index(row, view_col)
            existing = self.indexWidget(idx)
            if existing:
                existing.deleteLater()

        # 创建新按钮 — 紧凑尺寸，用独立QSS class覆盖全局按钮样式
        for row in range(self._proxy.rowCount()):
            proxy_idx = self._proxy.index(row, view_col)
            source_idx = self._proxy.mapToSource(proxy_idx)
            row_data = self._model.get_source_row_data(source_idx.row())

            btn = QPushButton("查看")
            btn.setObjectName("cellViewBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, rd=row_data: self._on_view_clicked(rd))
            self.setIndexWidget(proxy_idx, btn)

    def _on_view_clicked(self, row_data: dict):
        idx = row_data.get("_data_index", -1)
        self.view_clicked.emit(idx)

    # -- 覆写 populate / _on_header_clicked 以重建按钮 ----------------------

    def populate(self, data):
        super().populate(data)
        self._rebuild_view_buttons()

    def _on_header_clicked(self, col):
        super()._on_header_clicked(col)
        self._rebuild_view_buttons()
