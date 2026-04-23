# -*- coding: utf-8 -*-
"""数据查看器 — 产品表格 + 佣金表格"""

import os
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QLabel, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QStyledItemDelegate, QStyle, QMenu, QApplication
)
from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QPixmap, QColor, QPen, QPainter, QPixmapCache, QKeySequence

from src.models.database import DatabaseManager

logger = logging.getLogger(__name__)


# ── 缩略图 Delegate ────────────────────────────────


class ThumbnailDelegate(QStyledItemDelegate):
    """产品图片缩略图 — 48x48, 缓存, 无图占位"""

    THUMB_SIZE = 48

    def __init__(self, image_dir="", parent=None):
        super().__init__(parent)
        self._image_dir = image_dir

    def paint(self, painter, option, index):
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

        path = str(index.data(Qt.DisplayRole) or "").strip()
        thumb = self._load_thumbnail(path)
        if thumb and not thumb.isNull():
            x = option.rect.x() + (option.rect.width() - self.THUMB_SIZE) // 2
            y = option.rect.y() + (option.rect.height() - self.THUMB_SIZE) // 2
            painter.drawPixmap(x, y, thumb)
        else:
            r = QRect(option.rect.x() + 4, option.rect.y() + 4,
                       self.THUMB_SIZE, self.THUMB_SIZE)
            painter.setPen(QPen(QColor("#d9d9d9"), 1))
            painter.setBrush(QColor("#f5f5f5"))
            painter.drawRoundedRect(r, 4, 4)
            painter.setPen(QColor("#bfbfbf"))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "无图")
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(self.THUMB_SIZE + 8, self.THUMB_SIZE + 8)

    def _load_thumbnail(self, path):
        if not path:
            return QPixmap()
        if not os.path.isabs(path):
            path = os.path.join(self._image_dir, path)
        key = f"thumb:{path}"
        cached = QPixmapCache.find(key)
        if cached is not None:
            return cached
        if not os.path.isfile(path):
            return QPixmap()
        pm = QPixmap(path)
        if pm.isNull():
            return QPixmap()
        scaled = pm.scaled(self.THUMB_SIZE, self.THUMB_SIZE,
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
        QPixmapCache.insert(key, scaled)
        return scaled


# ── 产品表格 ──────────────────────────────────────


class ProductViewer(QWidget):
    """产品数据浏览面板"""

    # 列定义: (field_name, display_header, width)
    _PRODUCT_COLUMNS = [
        ("_seq", "序号", 45),
        ("sku_code", "货号", 120),
        ("chinese_name", "中文名称", 130),
        ("sheet_name", "来源Sheet", 85),
        ("category", "类目", 80),
        ("distribution_price", "分销价", 70),
        ("inventory", "库存数量", 60),
        ("inventory_status", "库存状态", 70),
        ("supplier", "供应商编码", 80),
        ("image_local_path", "图片", 58),
        ("weight", "重量", 55),
        ("dimensions", "尺寸", 75),
        ("brand", "品牌", 65),
    ]

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._loaded = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── 筛选栏 ──
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        filter_bar.addWidget(QLabel("搜索:"))
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("搜索 货号 / 名称...")
        self._search_box.setClearButtonEnabled(True)
        filter_bar.addWidget(self._search_box, stretch=1)

        filter_bar.addWidget(QLabel("来源Sheet:"))
        self._sheet_filter = QComboBox()
        self._sheet_filter.setMinimumWidth(130)
        self._sheet_filter.addItem("全部")
        filter_bar.addWidget(self._sheet_filter)

        layout.addLayout(filter_bar)

        # ── 表格 ──
        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.horizontalHeader().setStretchLastSection(True)

        # 图片列 delegate
        image_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "data", "image_cache")
        self._thumb_delegate = ThumbnailDelegate(image_dir)

        layout.addWidget(self._table)

        self._search_box.textChanged.connect(self._apply_filter)
        self._sheet_filter.currentIndexChanged.connect(self._apply_filter)

    def load_data(self):
        products = self.db.get_all_products()
        self.populate_sheet_filter(products)

        cols = self._PRODUCT_COLUMNS
        self._table.setRowCount(len(products))
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels([c[1] for c in cols])

        img_col = None
        for j, (field, _header, _width) in enumerate(cols):
            if field == "image_local_path":
                img_col = j

        for i, p in enumerate(products):
            for j, (field, _header, _width) in enumerate(cols):
                if field == "_seq":
                    text = str(i + 1)
                else:
                    val = getattr(p, field, "")
                    text = self._format_value(field, val)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(i, j, item)

        # 列宽
        for j, (_field, _header, width) in enumerate(cols):
            self._table.setColumnWidth(j, width)

        # 行高 — 给图片列留空间
        for i in range(self._table.rowCount()):
            self._table.setRowHeight(i, 56)

        # 安装图片 delegate
        if img_col is not None:
            self._table.setItemDelegateForColumn(img_col, self._thumb_delegate)

        self._loaded = True

    def refresh(self):
        self._loaded = False
        self.load_data()

    @property
    def table(self):
        return self._table

    def _on_table_context_menu(self, pos):
        """右键菜单 — 复制单元格内容"""
        item = self._table.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        copy_action = menu.addAction("复制")
        action = menu.exec(self._table.mapToGlobal(pos))
        if action == copy_action:
            clipboard = QApplication.clipboard()
            clipboard.setText(item.text())

    def keyPressEvent(self, event):
        """支持 Ctrl+C 复制选中单元格"""
        if event.matches(QKeySequence.Copy):
            item = self._table.currentItem()
            if item:
                clipboard = QApplication.clipboard()
                clipboard.setText(item.text())
        else:
            super().keyPressEvent(event)

    def populate_sheet_filter(self, products):
        current = self._sheet_filter.currentText()
        sheets = sorted(set(p.sheet_name for p in products if p.sheet_name))
        self._sheet_filter.blockSignals(True)
        self._sheet_filter.clear()
        self._sheet_filter.addItem("全部")
        self._sheet_filter.addItems(sheets)
        idx = self._sheet_filter.findText(current)
        if idx >= 0:
            self._sheet_filter.setCurrentIndex(idx)
        self._sheet_filter.blockSignals(False)

    @staticmethod
    def _format_value(field, val):
        if val is None:
            return "-"
        if field == "distribution_price":
            return f"{val:.2f}"
        if field == "weight":
            return f"{val:.3f}"
        if field == "inventory":
            return str(int(val)) if val is not None else "-"
        if field == "image_local_path":
            if val and isinstance(val, str):
                return os.path.basename(val) if val else ""
            return ""
        return str(val)

    def _apply_filter(self):
        search = self._search_box.text().strip().lower()
        sheet = self._sheet_filter.currentText()
        for row in range(self._table.rowCount()):
            sku_item = self._table.item(row, 1)    # col 1 = sku_code
            name_item = self._table.item(row, 2)    # col 2 = chinese_name
            sheet_item = self._table.item(row, 3)   # col 3 = sheet_name

            match_search = True
            if search:
                sku = sku_item.text().lower() if sku_item else ""
                name = name_item.text().lower() if name_item else ""
                match_search = search in sku or search in name

            match_sheet = True
            if sheet and sheet != "全部":
                s = sheet_item.text() if sheet_item else ""
                match_sheet = s == sheet

            self._table.setRowHidden(row, not (match_search and match_sheet))


# ── 佣金表格 ──────────────────────────────────────


class CommissionViewer(QWidget):
    """佣金数据浏览面板（搜索 + 宽表格）"""

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._loaded = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        search_bar = QHBoxLayout()
        search_bar.addWidget(QLabel("搜索:"))
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("搜索品类 / 商品名称...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._apply_filter)
        search_bar.addWidget(self._search_box, stretch=1)
        layout.addLayout(search_bar)

        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._table)

    def load_data(self):
        commissions = self.db.get_all_commissions()
        self._table.setRowCount(len(commissions))
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["品类", "商品", "佣金率%"])
        for i, c in enumerate(commissions):
            self._table.setItem(i, 0, QTableWidgetItem(c.category))
            self._table.setItem(i, 1, QTableWidgetItem(c.product))
            item_rate = QTableWidgetItem(f"{c.rate:.1f}")
            item_rate.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 2, item_rate)
        self._table.resizeColumnsToContents()
        self._loaded = True

    def refresh(self):
        self._loaded = False
        self.load_data()

    def _apply_filter(self):
        search = self._search_box.text().strip().lower()
        if not search:
            for row in range(self._table.rowCount()):
                self._table.setRowHidden(row, False)
            return
        for row in range(self._table.rowCount()):
            cat_item = self._table.item(row, 0)
            prod_item = self._table.item(row, 1)
            cat = cat_item.text().lower() if cat_item else ""
            prod = prod_item.text().lower() if prod_item else ""
            self._table.setRowHidden(row, not (search in cat or search in prod))


# ── 兼容层 ────────────────────────────────────────


class DataViewerWidget(QWidget):
    """兼容旧接口"""

    def __init__(self, db: DatabaseManager, sync_widget=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._sync_widget = sync_widget
        self._product_viewer = ProductViewer(db, self)
        self._commission_viewer = CommissionViewer(db, self)

    def refresh_products(self):
        self._product_viewer.refresh()

    def refresh_commissions(self):
        self._commission_viewer.refresh()

    @property
    def product_viewer(self):
        return self._product_viewer

    @property
    def commission_viewer(self):
        return self._commission_viewer
