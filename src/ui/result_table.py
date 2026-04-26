# -*- coding: utf-8 -*-
"""结果表格组件 — QTableView + BaseTableModel 架构，带多优先级行颜色 + 库存状态单元格覆盖。"""

from PySide6.QtCore import Qt

from src.ui.table_base import BaseTableModel, BaseTableView, ThemeColors


# ---------------------------------------------------------------------------
# ResultModel
# ---------------------------------------------------------------------------

class ResultModel(BaseTableModel):
    """结果数据模型 — 精简后的运营结果视图。"""

    COLUMNS = [
        ("seller_sku", "卖家货号", 150),
        ("category", "类目", 100),
        ("current_price", "原价", 80),
        ("discounted_price", "折后价格", 80),
        ("inventory_status", "库存状态", 90),
        ("cost_matched", "SKU匹配", 72),
        ("commission_source", "佣金匹配", 120),
        ("product_cost", "产品成本", 80),
        ("shipping_fee", "运费", 70),
        ("breakeven", "保本价", 80),
        ("profit", "盈亏额", 80),
        ("target_discount", "目标折扣", 70),
        ("target_price", "目标价格", 80),
    ]

    def __init__(self, parent=None):
        super().__init__(self.COLUMNS, parent)

    # -- 格式化 -------------------------------------------------------------

    def _format_value(self, row: int, col: int) -> str:
        col_key = self._col_key(col)
        val = self._data[row].get(col_key) if row < len(self._data) else None

        if val is None:
            return "-"
        if col_key == "inventory_status":
            return str(val) if val else "-"
        if col_key == "cost_matched":
            return "✅" if val else "❌"
        if col_key == "commission_source":
            return str(val) if val else "-"
        if col_key == "target_discount":
            try:
                return f"{int(float(val))}%"
            except (ValueError, TypeError):
                return "-"
        if col_key == "target_price":
            try:
                return f"{float(val):.2f}"
            except (ValueError, TypeError):
                return "-"
        if col_key in ("current_price", "discounted_price", "product_cost", "shipping_fee",
                        "breakeven", "profit", "target_price"):
            try:
                return f"{float(val):.2f}"
            except (ValueError, TypeError):
                return str(val) if val else "-"
        return str(val) if val else "-"

    # -- 颜色 ---------------------------------------------------------------

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return self._format_value(index.row(), index.column())

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter

        if role == Qt.ItemDataRole.BackgroundRole:
            return self._background(index)

        if role == Qt.ItemDataRole.ForegroundRole:
            return self._foreground(index)

        return None

    def _background(self, index):
        """BackgroundRole — 多优先级行颜色 + 库存状态单元格覆盖。"""
        row_data = self._data[index.row()]
        col_key = self._col_key(index.column())
        val = row_data.get(col_key)

        # 1. 库存状态单元格覆盖 — 该单元格最高优先级
        if col_key == "inventory_status" and val:
            colors = ThemeColors.stock_status_colors().get(str(val))
            if colors:
                return colors[0]  # bg color

        # 2. 行级颜色 (优先级: SKU未匹配 > 类目未匹配 > 盈利 > 亏损)
        cost_matched = row_data.get("cost_matched", True)
        if cost_matched is False:
            return ThemeColors.row_no_sku()

        category_matched = row_data.get("category_matched", True)
        if category_matched is False:
            return ThemeColors.row_no_category()

        profit = row_data.get("profit")
        if isinstance(profit, (int, float)):
            if profit > 0:
                return ThemeColors.row_profit()
            elif profit < 0:
                return ThemeColors.row_loss()

        return None  # QSS handles default + alternating

    def _foreground(self, index):
        """ForegroundRole — 行级前景色 + 利润列 + 库存状态单元格颜色。"""
        col_key = self._col_key(index.column())
        row_data = self._data[index.row()]
        val = row_data.get(col_key)

        # 1. 库存状态单元格前景色
        if col_key == "inventory_status" and val:
            colors = ThemeColors.stock_status_colors().get(str(val))
            if colors:
                return colors[1]  # fg color

        # 2. 利润列文字颜色
        if col_key == "profit" and isinstance(val, (int, float)):
            if val > 0:
                return ThemeColors.profit_fg()
            elif val < 0:
                return ThemeColors.loss_fg()

        # 3. 有背景色的行 → 用高对比度前景色（解决浅背景+白字看不清的问题）
        bg = self._background(index)
        if bg is not None:
            return ThemeColors.row_fg()

        return None


# ---------------------------------------------------------------------------
# ResultTable
# ---------------------------------------------------------------------------

class ResultTable(BaseTableView):
    """结果表格视图 — 继承 BaseTableView 的 3 态排序 + 右键列筛选。"""

    MATCH_COLUMN_KEYS = {"shipping_fee", "inventory_status",
                         "cost_matched", "commission_source", "product_cost"}
    CALC_COLUMN_KEYS = {"breakeven", "profit", "target_discount", "target_price"}

    def __init__(self, parent=None):
        model = ResultModel()
        super().__init__(model, parent)
        self.setObjectName("resultTable")
        self._results = []  # Backward compat
        self._set_column_widths()

    def load_results(self, results: list):
        self._results = results
        self.populate(results)

    def get_results(self):
        return self._results

    def clear_results(self):
        self._results = []
        self.clear_data()

    def clear_all_filters(self):
        self._proxy.clear_all_filters()
        self._sort_states.clear()
        header = self.horizontalHeader()
        header.setSortIndicatorShown(False)

    def update_match_columns(self, data: list):
        self._results = data
        super().update_match_columns(data)

    def update_calc_columns(self, data: list):
        self._results = data
        super().update_calc_columns(data)
