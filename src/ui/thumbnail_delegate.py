# -*- coding: utf-8 -*-
"""图片缩略图渲染组件 — 在 QTableWidget 单元格中显示产品图片"""

import os
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem
from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QPixmap, QColor, QPen, QPainter, QPixmapCache


class ThumbnailDelegate(QStyledItemDelegate):
    """产品图片缩略图 Delegate

    - 从 image_local_path 加载图片，缩放到 48×48
    - 使用 QPixmapCache 缓存缩略图
    - 无图片时绘制灰色占位框 + "无图" 文字
    """

    THUMB_SIZE = 48
    CELL_PAD = 4

    def __init__(self, image_dir: str = "", parent=None):
        super().__init__(parent)
        self._image_dir = image_dir  # base dir for relative paths

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()

        # background
        if option.state & QStyleOptionViewItem.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

        path = index.data(Qt.DisplayRole)
        if path is None:
            path = ""
        path = str(path).strip()

        thumb = self._load_thumbnail(path)
        if thumb and not thumb.isNull():
            x = option.rect.x() + (option.rect.width() - self.THUMB_SIZE) // 2
            y = option.rect.y() + (option.rect.height() - self.THUMB_SIZE) // 2
            painter.drawPixmap(x, y, thumb)
        else:
            self._draw_placeholder(painter, option.rect)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(self.THUMB_SIZE + 2 * self.CELL_PAD,
                     self.THUMB_SIZE + 2 * self.CELL_PAD)

    # ── private ───────────────────────────────

    def _load_thumbnail(self, path: str) -> QPixmap:
        """Load and cache a thumbnail."""
        if not path:
            return QPixmap()

        # resolve absolute path
        if not os.path.isabs(path):
            path = os.path.join(self._image_dir, path)

        cache_key = f"thumb:{path}"

        cached = QPixmapCache.find(cache_key)
        if cached is not None:
            return cached

        if not os.path.isfile(path):
            return QPixmap()

        pm = QPixmap(path)
        if pm.isNull():
            return QPixmap()

        scaled = pm.scaled(
            self.THUMB_SIZE, self.THUMB_SIZE,
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        QPixmapCache.insert(cache_key, scaled)
        return scaled

    def _draw_placeholder(self, painter: QPainter, rect: QRect):
        """Draw '无图' placeholder."""
        inner = QRect(
            rect.x() + self.CELL_PAD,
            rect.y() + self.CELL_PAD,
            self.THUMB_SIZE, self.THUMB_SIZE
        )
        painter.setPen(QPen(QColor("#d9d9d9"), 1))
        painter.setBrush(QColor("#f5f5f5"))
        painter.drawRoundedRect(inner, 4, 4)

        painter.setPen(QColor("#bfbfbf"))
        painter.setFont(painter.font())
        painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, "无图")
