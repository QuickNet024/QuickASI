# -*- coding: utf-8 -*-
"""匹配数据表格组件 — 显示中间匹配结果（SKU匹配、佣金匹配、库存状态等）"""

from PySide6.QtCore import Qt

from src.ui.table_base import (
    BaseTableModel, BaseTableView, ThemeColors,
)

# 列定义: (key, title, width)
COLUMNS = [
    ("row_number", "行号", 50),
    ("seller_sku", "卖家货号", 150),
    ("category", "类目", 80),
    ("sku_matched", "SKU匹配", 70),
    ("matched_product_id", "匹配产品ID", 100),
    ("product_category", "产品类目", 100),
    ("dimensions", "尺寸", 100),
    ("wb_stock", "WB库存", 70),
    ("seller_stock", "卖家库存", 70),
    ("inventory_status", "库存状态", 90),
    ("commission_rate", "佣金率", 70),
    ("category_matched", "类目匹配", 70),
    ("product_cost", "产品成本", 80),
    ("distribution_price", "分销价格", 80),
    ("shipping_fee", "产品运费", 80),
    ("volume", "容积(L)", 80),
    ("density", "密度(kg/L)", 90),
    ("weight", "包装重量(kg)", 100),
]


class MatchDataModel(BaseTableModel):
    """匹配数据表格模型 — 管理18列匹配中间结果数据。"""

    def __init__(self, parent=None):
        super().__init__(COLUMNS, parent)

    # -- 格式化 ---------------------------------------------------------------

    def _format_value(self, row: int, col: int) -> str:
        key = self._col_key(col)
        val = self._col_value(self._data[row], col)

        if val is None:
            return "-"

        # Boolean fields
        if key in ("sku_matched", "category_matched"):
            if val is True:
                return "✅"
            if val is False:
                return "❌"
            return str(val)

        # Inventory status
        if key == "inventory_status":
            return str(val) if val else "-"

        # Commission rate
        if key == "commission_rate":
            try:
                return f"{int(float(val))}%"
            except (ValueError, TypeError):
                return str(val) if val else "-"

        # Product cost / distribution price / shipping fee
        if key in ("product_cost", "distribution_price", "shipping_fee"):
            try:
                return f"{float(val):.2f}"
            except (ValueError, TypeError):
                return str(val) if val else "-"

        # Density
        if key == "density":
            try:
                val_f = float(val)
                return f"{val_f:.3f}" if val_f > 0 else "-"
            except (ValueError, TypeError):
                return str(val) if val else "-"

        # Weight
        if key == "weight":
            try:
                val_f = float(val)
                return f"{val_f:.3f}" if val_f > 0 else "-"
            except (ValueError, TypeError):
                return str(val) if val else "-"

        # Stock fields
        if key in ("wb_stock", "seller_stock"):
            return str(val) if val else "-"

        # Volume
        if key == "volume":
            try:
                return f"{float(val):.3f}" if val else "-"
            except (ValueError, TypeError):
                return str(val) if val else "-"

        # Default
        return str(val) if val is not None and val != "" else "-"

    # -- 颜色 -----------------------------------------------------------------

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        key = self._col_key(col)
        val = self._col_value(self._data[row], col)

        if role == Qt.ItemDataRole.BackgroundRole:
            # Inventory status cell color takes priority
            if key == "inventory_status" and val and str(val) in ThemeColors.stock_status_colors():
                bg, _ = ThemeColors.stock_status_colors()[str(val)]
                return bg
            # Row-level color based on match status
            if self._col_value(self._data[row], col) is not None or key in ("sku_matched",):
                sku_ok = self._data[row].get("sku_matched", True)
                cat_ok = self._data[row].get("category_matched", True)
                if sku_ok is False:
                    return ThemeColors.row_no_sku()
                if cat_ok is False:
                    return ThemeColors.row_no_category()
            return None

        if role == Qt.ItemDataRole.ForegroundRole:
            if key == "inventory_status" and val and str(val) in ThemeColors.stock_status_colors():
                _, fg = ThemeColors.stock_status_colors()[str(val)]
                return fg
            # 有背景色的行 → 用高对比度前景色
            bg = None
            if self._col_value(self._data[row], col) is not None or key in ("sku_matched",):
                sku_ok = self._data[row].get("sku_matched", True)
                cat_ok = self._data[row].get("category_matched", True)
                if sku_ok is False:
                    bg = ThemeColors.row_no_sku()
                elif cat_ok is False:
                    bg = ThemeColors.row_no_category()
            if bg is not None:
                return ThemeColors.row_fg()
            return None

        return super().data(index, role)


class MatchDataTable(BaseTableView):
    """匹配数据表格 — 显示SKU匹配、佣金匹配、库存等中间结果。

    公共 API:
        populate(data)           — 加载全部数据
        update_match_columns(d)  — 按行合并更新匹配列
        clear_match_columns()    — 清空匹配列
        clear_data()             — 清空全部数据
    """

    MATCH_COLUMN_KEYS = {
        "sku_matched", "matched_product_id", "product_category", "dimensions",
        "wb_stock", "seller_stock", "inventory_status", "commission_rate",
        "category_matched", "product_cost", "distribution_price",
        "shipping_fee", "volume", "density", "weight",
    }

    def __init__(self, parent=None):
        model = MatchDataModel()
        super().__init__(model, parent)
        self.setObjectName("matchTable")
        self._set_column_widths()

    def clear_match_columns(self):
        """Set all match columns to None (display as "-")."""
        self._model.clear_columns(self.MATCH_COLUMN_KEYS)

    def refresh_theme(self):
        """Force repaint after theme switch to update ThemeColors."""
        self.viewport().update()
