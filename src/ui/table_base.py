# -*- coding: utf-8 -*-
"""共享表格基础组件 — QTableView + QAbstractTableModel 架构的公共基类。

包含 BaseTableModel、ColumnFilterProxyModel、BaseTableView，
供 match_data_table / result_table / calc_data_table / data_viewers 四张表继承。
"""

from PySide6.QtCore import QAbstractTableModel, QSortFilterProxyModel, Qt, QModelIndex
from PySide6.QtWidgets import QTableView, QHeaderView, QMenu, QAbstractItemView
from PySide6.QtGui import QColor, QAction, QActionGroup


# ---------------------------------------------------------------------------
# BaseTableModel
# ---------------------------------------------------------------------------

class BaseTableModel(QAbstractTableModel):
    """抽象表格模型基类。

    子类必须:
    - 传入 columns 定义 (key, title, width)
    - 实现 _format_value(row, col) -> str
    """

    def __init__(self, columns: list[tuple[str, str, int]], parent=None):
        super().__init__(parent)
        self.COLUMNS: list[tuple[str, str, int]] = columns
        self._data: list[dict] = []

    # -- QAbstractTableModel 必须实现 ---------------------------------------

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.COLUMNS[section][1]
            return section + 1  # 行号从 1 开始
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if orientation == Qt.Orientation.Horizontal:
                return Qt.AlignmentFlag.AlignCenter
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._format_value(index.row(), index.column())
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        if role == Qt.ItemDataRole.BackgroundRole:
            return None  # 子类覆写
        if role == Qt.ItemDataRole.ForegroundRole:
            return None  # 子类覆写
        return None

    def flags(self, index):
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    # -- 子类必须实现 -------------------------------------------------------

    def _format_value(self, row: int, col: int) -> str:
        raise NotImplementedError

    # -- 内部工具方法 -------------------------------------------------------

    def _col_key(self, col: int) -> str:
        return self.COLUMNS[col][0]

    def _col_value(self, row_data: dict, col: int):
        return row_data.get(self._col_key(col))

    # -- 数据操作 -----------------------------------------------------------

    def set_data(self, new_data: list[dict]):
        self.beginResetModel()
        self._data = new_data
        self.endResetModel()

    def update_columns(self, keys: set, new_data: list[dict]):
        """按行索引合并更新 — 只修改 keys 集合内的字段，保留其余字段不变。"""
        self.beginResetModel()
        for i, new_row in enumerate(new_data):
            if i < len(self._data):
                for k in keys:
                    if k in new_row:
                        self._data[i][k] = new_row[k]
        self.endResetModel()

    def clear_columns(self, keys: set):
        self.beginResetModel()
        for row in self._data:
            for k in keys:
                row[k] = None
        self.endResetModel()

    def clear_data(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def get_source_row_data(self, source_row: int) -> dict:
        return self._data[source_row]


# ---------------------------------------------------------------------------
# ColumnFilterProxyModel
# ---------------------------------------------------------------------------

class ColumnFilterProxyModel(QSortFilterProxyModel):
    """带列值筛选的代理模型，在 QSortFilterProxyModel 排序基础上增加按列值过滤。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._col_filters: dict[int, set[str]] = {}
        self._numeric_filters: dict[int, tuple] = {}  # col -> (op, val)
        self._search_text: str = ""  # global text search across all columns
        self.setSortRole(Qt.ItemDataRole.DisplayRole)

    def _refresh_filters(self):
        """Refresh proxy filters with Qt6-compatible API when available."""
        begin = getattr(self, "beginFilterChange", None)
        end = getattr(self, "endFilterChange", None)
        if callable(begin) and callable(end):
            begin()
            try:
                end(QSortFilterProxyModel.Direction.Rows)
            except Exception:
                end()
            return
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):  # noqa: N802
        source_model = self.sourceModel()
        # Global text search
        if self._search_text:
            found = False
            for col in range(source_model.columnCount()):
                idx = source_model.index(source_row, col)
                val = str(source_model.data(idx, Qt.ItemDataRole.DisplayRole) or "").lower()
                if self._search_text in val:
                    found = True
                    break
            if not found:
                return False
        # Column value filters
        for col_idx, allowed_values in self._col_filters.items():
            index = source_model.index(source_row, col_idx)
            val = str(source_model.data(index, Qt.ItemDataRole.DisplayRole) or "").strip()
            if val not in allowed_values:
                return False
        # Numeric filters
        for col_idx, (op, threshold) in self._numeric_filters.items():
            index = source_model.index(source_row, col_idx)
            raw = source_model.data(index, Qt.ItemDataRole.DisplayRole)
            try:
                val = float(str(raw).replace(",", "").replace("%", "").strip())
            except (ValueError, TypeError):
                return False
            if op == "<" and not (val < threshold):
                return False
            elif op == "<=" and not (val <= threshold):
                return False
            elif op == ">" and not (val > threshold):
                return False
            elif op == ">=" and not (val >= threshold):
                return False
            elif op == "==" and not (val == threshold):
                return False
        return True

    def set_column_filter(self, col: int, values: set[str]):
        self._col_filters[col] = values
        self._refresh_filters()

    def clear_column_filter(self, col: int):
        self._col_filters.pop(col, None)
        self._refresh_filters()

    def set_numeric_filter(self, col: int, op: str, value: float):
        """Set numeric filter: op is '<', '<=', '>', '>=', '=='."""
        self._numeric_filters[col] = (op, value)
        self._refresh_filters()

    def clear_numeric_filter(self, col: int):
        self._numeric_filters.pop(col, None)
        self._refresh_filters()

    def set_search_text(self, text: str):
        """Set global search text (case-insensitive, matches any column)."""
        self._search_text = text.strip().lower()
        self._refresh_filters()

    def clear_all_filters(self):
        self._col_filters.clear()
        self._numeric_filters.clear()
        self._search_text = ""
        self._refresh_filters()

    def filter_column_unique_values(self, col: int) -> list[str]:
        source = self.sourceModel()
        values: set[str] = set()
        for row in range(source.rowCount()):
            idx = source.index(row, col)
            val = str(source.data(idx, Qt.ItemDataRole.DisplayRole) or "").strip()
            values.add(val)
        return sorted(values)

    def lessThan(self, left, right):  # noqa: N802
        left_val = self.sourceModel().data(left, Qt.ItemDataRole.DisplayRole)
        right_val = self.sourceModel().data(right, Qt.ItemDataRole.DisplayRole)
        left_str = str(left_val or "")
        right_str = str(right_val or "")
        try:
            return float(left_str) < float(right_str)
        except (ValueError, TypeError):
            return left_str < right_str


# ---------------------------------------------------------------------------
# BaseTableView
# ---------------------------------------------------------------------------

# 颜色常量
STOCK_STATUS_COLORS = {
    "货源充足": (QColor("#e6f7e6"), QColor("#1a7a1a")),
    "停止上架": (QColor("#ffe6e6"), QColor("#c91a2a")),
    "货源紧缺": (QColor("#fff3cd"), QColor("#856404")),
    "等待补货": (QColor("#ffe8cc"), QColor("#b35900")),
}
COLOR_PROFIT_FG = QColor(56, 158, 13)
COLOR_LOSS_FG = QColor(207, 19, 34)
COLOR_ROW_NO_SKU = QColor("#ffe6e6")
COLOR_ROW_NO_CATEGORY = QColor("#fff3e0")
COLOR_ROW_PROFIT = QColor("#e6f7e6")
COLOR_ROW_LOSS = QColor("#ffe6e6")


class BaseTableView(QTableView):
    """共享表格视图基类 — 3 态排序 + 右键列筛选 + 通用视图设置。

    子类需:
    - 定义 MATCH_COLUMN_KEYS / CALC_COLUMN_KEYS (可选)
    - 添加到 _filter_skip_keys 需要跳过滤菜单的列 (如 _view)
    - 覆写颜色相关方法 (如 data() 中的 BackgroundRole/ForegroundRole 在 model 侧处理)
    """

    AUTO_FIT_SAMPLE_LIMIT = 200

    def __init__(self, model: BaseTableModel, parent=None):
        super().__init__(parent)
        self._model = model
        self._proxy = ColumnFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self.setModel(self._proxy)

        self._sort_states: dict[int, int] = {}  # col_idx → 0=none, 1=asc, 2=desc
        self._filter_skip_keys: set = set()      # 子类可添加要跳过滤菜单的 key

        self._setup_view()

    # -- 视图初始化 ---------------------------------------------------------

    def _setup_view(self):
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)

        header = self.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(False)  # 我们自己管理排序指示器
        header.sectionClicked.connect(self._on_header_clicked)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)

    def _set_column_widths(self):
        header = self.horizontalHeader()
        for col_idx, (_, _, width) in enumerate(self._model.COLUMNS):
            header.resizeSection(col_idx, width)
        # Switch to fixed (Interactive) mode so Qt doesn't auto-resize on data changes
        # This is critical for performance with large datasets
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    # -- 3 态排序 -----------------------------------------------------------

    def _on_header_clicked(self, col: int):
        if col == 0:  # 行号列不参与排序
            return
        # Reset all other columns' sort states — only one column sorted at a time
        for other_col in list(self._sort_states.keys()):
            if other_col != col:
                self._sort_states[other_col] = 0
        current = self._sort_states.get(col, 0)
        if current == 0:
            self._sort_states[col] = 1  # asc
            self._proxy.sort(col, Qt.SortOrder.AscendingOrder)
        elif current == 1:
            self._sort_states[col] = 2  # desc
            self._proxy.sort(col, Qt.SortOrder.DescendingOrder)
        else:
            self._sort_states[col] = 0  # none
            self._proxy.sort(-1, Qt.SortOrder.AscendingOrder)

        header = self.horizontalHeader()
        state = self._sort_states.get(col, 0)
        if state == 0:
            header.setSortIndicatorShown(False)
        else:
            header.setSortIndicatorShown(True)
            order = Qt.SortOrder.AscendingOrder if state == 1 else Qt.SortOrder.DescendingOrder
            header.setSortIndicator(col, order)

    # -- 右键筛选菜单 -------------------------------------------------------

    def _on_header_context_menu(self, pos):
        col = self.horizontalHeader().logicalIndexAt(pos)
        if col < 0 or col >= len(self._model.COLUMNS):
            return
        key = self._model.COLUMNS[col][0]
        if key in self._filter_skip_keys:
            return
        global_pos = self.horizontalHeader().mapToGlobal(pos)
        self._show_column_filter_menu(col, global_pos)

    def _show_column_filter_menu(self, col: int, global_pos):
        header_name = self._model.COLUMNS[col][1]
        unique_values = self._proxy.filter_column_unique_values(col)
        if not unique_values:
            return

        menu = QMenu(self)
        menu.setWindowTitle(f"筛选: {header_name}")

        select_all_action = QAction("全选", self)
        clear_action = QAction("清除筛选", self)
        menu.addAction(select_all_action)
        menu.addAction(clear_action)
        menu.addSeparator()

        current_allowed = self._proxy._col_filters.get(col)
        group = QActionGroup(self)
        group.setExclusive(False)
        val_actions: dict[QAction, str] = {}

        for val in unique_values:
            display = val if val else "(空)"
            action = QAction(display, self)
            action.setCheckable(True)
            if current_allowed is None:
                action.setChecked(True)
            else:
                action.setChecked(val in current_allowed)
            menu.addAction(action)
            group.addAction(action)
            val_actions[action] = val

        menu.addSeparator()
        apply_action = QAction("✓ 应用筛选", self)
        menu.addAction(apply_action)

        chosen = menu.exec(global_pos)
        if chosen == apply_action:
            checked_values = {v for a, v in val_actions.items() if a.isChecked()}
            if len(checked_values) == len(unique_values) or not checked_values:
                self._proxy.clear_column_filter(col)
            else:
                self._proxy.set_column_filter(col, checked_values)
        elif chosen in (select_all_action, clear_action):
            self._proxy.clear_column_filter(col)

    # -- 公共 API (子类调用) ------------------------------------------------

    def populate(self, data: list[dict]):
        self._model.set_data(data)
        self._auto_fit_columns()

    def _auto_fit_columns(self):
        """Auto-fit all columns to content, then switch to Interactive for user resizing."""
        header = self.horizontalHeader()
        skip_keys = getattr(self, '_filter_skip_keys', set())
        if self._model.rowCount() > self.AUTO_FIT_SAMPLE_LIMIT:
            for col_idx, (key, _, defined_w) in enumerate(self._model.COLUMNS):
                if key in skip_keys:
                    continue
                header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)
                header.resizeSection(col_idx, defined_w)
            return
        # First pass: resize to content
        for col_idx, (key, _, _) in enumerate(self._model.COLUMNS):
            if key in skip_keys:
                continue
            header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.ResizeToContents)
        # Let Qt process the resize
        min_widths = []
        for col_idx in range(len(self._model.COLUMNS)):
            min_widths.append(header.sectionSize(col_idx))
        # Apply: use max of content width and defined width
        for col_idx, (key, _, defined_w) in enumerate(self._model.COLUMNS):
            if key in skip_keys:
                continue
            actual_w = max(min_widths[col_idx], defined_w)
            header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(col_idx, actual_w)

    def update_match_columns(self, data: list[dict]):
        if hasattr(self, "MATCH_COLUMN_KEYS"):
            self._model.update_columns(self.MATCH_COLUMN_KEYS, data)

    def update_calc_columns(self, data: list[dict]):
        if hasattr(self, "CALC_COLUMN_KEYS"):
            self._model.update_columns(self.CALC_COLUMN_KEYS, data)

    def clear_calc_columns(self):
        if hasattr(self, "CALC_COLUMN_KEYS"):
            self._model.clear_columns(self.CALC_COLUMN_KEYS)

    def clear_data(self):
        self._model.clear_data()
        self._proxy.clear_all_filters()
        self._sort_states.clear()
