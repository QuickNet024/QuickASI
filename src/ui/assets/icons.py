# -*- coding: utf-8 -*-
"""现代 SVG 矢量图标 — Material Design 风格

每个图标为 SVG 字符串模板，COLOR 占位符在渲染时替换为实际颜色。
纯 PySide6 实现，无外部依赖。
"""

# ── 飞书数据: 表格/数据网格图标 ──
ICON_DATA_TABLE = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="1.8"
  stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="18" height="18" rx="2"/>
  <line x1="3" y1="9" x2="21" y2="9"/>
  <line x1="3" y1="15" x2="21" y2="15"/>
  <line x1="9" y1="3" x2="9" y2="21"/>
  <line x1="15" y1="3" x2="15" y2="21"/>
</svg>"""

# ── 佣金数据: 百分比/标签图标 ──
ICON_COMMISSION = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="1.8"
  stroke-linecap="round" stroke-linejoin="round">
  <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/>
  <line x1="7" y1="7" x2="7.01" y2="7"/>
</svg>"""

# ── 汇率数据: 交换/货币图标 ──
ICON_EXCHANGE = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="1.8"
  stroke-linecap="round" stroke-linejoin="round">
  <path d="M17 1l4 4-4 4"/>
  <path d="M3 11V9a4 4 0 014-4h14"/>
  <path d="M7 23l-4-4 4-4"/>
  <path d="M21 13v2a4 4 0 01-4 4H3"/>
</svg>"""

# ── 模块ID → SVG 映射 ──
MODULE_ICONS = {
    "feishu": ICON_DATA_TABLE,
    "commission": ICON_COMMISSION,
    "exchange_rate": ICON_EXCHANGE,
}

# ── 模块ID → accent 颜色 ──
MODULE_COLORS = {
    "feishu": "#6366F1",       # Indigo-500
    "commission": "#10B981",   # Emerald-500
    "exchange_rate": "#F59E0B", # Amber-500
}

# 灰色（用于接口管理对话框等无颜色上下文）
COLOR_MUTED = "#9CA3AF"


def get_icon_svg(module_id: str, color: str = None) -> str:
    """获取模块的 SVG 字符串（已替换颜色）"""
    svg = MODULE_ICONS.get(module_id, ICON_DATA_TABLE)
    c = color or MODULE_COLORS.get(module_id, COLOR_MUTED)
    return svg.replace("COLOR", c)


def get_icon_pixmap(module_id: str, size: int = 24, color: str = None):
    """获取模块的 QPixmap 图标（需要 QGuiApplication 已创建）"""
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import QByteArray

    # 检查是否有 QGuiApplication（没有则返回空）
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        return QPixmap()

    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtGui import QPainter, QImage
    from PySide6.QtCore import Qt

    svg_data = get_icon_svg(module_id, color)
    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    if not renderer.isValid():
        return QPixmap()

    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(img)


def get_icon(module_id: str, size: int = 24, color: str = None):
    """获取模块的 QIcon"""
    from PySide6.QtGui import QIcon
    px = get_icon_pixmap(module_id, size, color)
    return QIcon(px)
