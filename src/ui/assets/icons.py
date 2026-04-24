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

# ── 运费配置: 包裹/箱图标 ──
ICON_SHIPPING = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="1.8"
  stroke-linecap="round" stroke-linejoin="round">
  <path d="M16.5 9.4l-9-5.19"/>
  <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>
  <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
  <line x1="12" y1="22.08" x2="12" y2="12"/>
</svg>"""

# ── 模块ID → SVG 映射 ──
MODULE_ICONS = {
    "feishu": ICON_DATA_TABLE,
    "commission": ICON_COMMISSION,
    "exchange_rate": ICON_EXCHANGE,
    "shipping": ICON_SHIPPING,
}

# ── 模块ID → accent 颜色 ──
MODULE_COLORS = {
    "feishu": "#6366F1",       # Indigo-500
    "commission": "#10B981",   # Emerald-500
    "exchange_rate": "#F59E0B", # Amber-500
    "shipping": "#3B82F6",     # Blue-500
}

# 灰色（用于接口管理对话框等无颜色上下文）
COLOR_MUTED = "#9CA3AF"

# ═══════════════════════════════════════════════
# 通用 UI 图标 (Material Design 风格，stroke-based)
# ═══════════════════════════════════════════════

ICON_REFRESH = """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round">
  <polyline points="23 4 23 10 17 10"/>
  <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
</svg>"""

ICON_SETTINGS = """<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"/>
  <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
</svg>"""

ICON_SHEET = """<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round">
  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
  <polyline points="14 2 14 8 20 8"/>
  <line x1="8" y1="13" x2="16" y2="13"/>
  <line x1="8" y1="17" x2="16" y2="17"/>
</svg>"""

ICON_LINK = """<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round">
  <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
  <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
</svg>"""

ICON_SLIDERS = """<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round">
  <line x1="4" y1="21" x2="4" y2="14"/>
  <line x1="4" y1="10" x2="4" y2="3"/>
  <line x1="12" y1="21" x2="12" y2="12"/>
  <line x1="12" y1="8" x2="12" y2="3"/>
  <line x1="20" y1="21" x2="20" y2="16"/>
  <line x1="20" y1="12" x2="20" y2="3"/>
  <line x1="1" y1="14" x2="7" y2="14"/>
  <line x1="9" y1="8" x2="15" y2="8"/>
  <line x1="17" y1="16" x2="23" y2="16"/>
</svg>"""

ICON_CLOSE = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round">
  <line x1="18" y1="6" x2="6" y2="18"/>
  <line x1="6" y1="6" x2="18" y2="18"/>
</svg>"""

ICON_IMAGE = """<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"
  viewBox="0 0 24 24" fill="none" stroke="COLOR" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="18" height="18" rx="2"/>
  <circle cx="8.5" cy="8.5" r="1.5"/>
  <polyline points="21 15 16 10 5 21"/>
</svg>"""

# ── 通用图标渲染 ──

def _render_svg(svg_template: str, size: int = 20, color: str = None):
    """渲染任意 SVG 模板为 QPixmap"""
    from PySide6.QtGui import QPixmap, QPainter, QImage
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtSvg import QSvgRenderer

    if QApplication.instance() is None:
        return QPixmap()

    c = color or COLOR_MUTED
    svg_data = svg_template.replace("COLOR", c)
    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    if not renderer.isValid():
        return QPixmap()

    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(img)


def get_util_icon(name: str, size: int = 20, color: str = None):
    """获取通用 UI 图标的 QPixmap。
    name: 'refresh', 'settings', 'sheet', 'link', 'sliders', 'close', 'image'
    """
    icons = {
        "refresh": ICON_REFRESH,
        "settings": ICON_SETTINGS,
        "sheet": ICON_SHEET,
        "link": ICON_LINK,
        "sliders": ICON_SLIDERS,
        "close": ICON_CLOSE,
        "image": ICON_IMAGE,
    }
    svg = icons.get(name)
    if not svg:
        return _render_svg(ICON_SETTINGS, size, color)
    return _render_svg(svg, size, color)


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
