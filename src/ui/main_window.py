# -*- coding: utf-8 -*-
"""主窗口 - QMainWindow + 侧边栏导航 + 顶栏 + QStackedWidget 布局"""

import os
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QWidget, QVBoxLayout,
    QFileDialog, QMessageBox,
    QStatusBar, QLabel, QProgressBar, QStackedWidget
)
from PySide6.QtCore import Qt, QThread, Signal

from src.config import Config
from src.models.database import DatabaseManager
from src.services.calculator import LossCalculator, CalculationParams
from src.services.excel_service import ExcelService
from src.services.matcher import ProductMatcher
from src.services.commission_svc import CommissionService
from src.services.exchange_rate import ExchangeRateService

from src.ui.sidebar import SideBar
from src.ui.top_bar import TopBar
from src.ui.sync_widget import SyncWidget
from src.ui.data_viewers import ProductViewer, CommissionViewer
from src.ui.discount_calc_widget import DiscountCalcWidget
from src.ui.settings_dialog import SettingsDialog
from src.ui.theme_manager import ThemeManager
from src.version import get_app_version, get_version_text

logger = logging.getLogger(__name__)

# Page indices in QStackedWidget
PAGE_SYNC = 0
PAGE_PRODUCTS = 1
PAGE_COMMISSIONS = 2
PAGE_DISCOUNT_CALC = 3
PAGE_SETTINGS = 4


class CalculateWorker(QThread):
    """后台计算线程"""
    progress = Signal(int, int)      # current, total
    finished = Signal(list)           # results list
    error = Signal(str)

    def __init__(self, rows, params_dict, db: DatabaseManager,
                  strategy: str, mode: str, cny_to_rub: float):
        super().__init__()
        self.rows = rows
        self.params_dict = params_dict
        self.db = db
        self.strategy = strategy
        self.mode = mode
        self.cny_to_rub = cny_to_rub

    def run(self):
        try:
            params = CalculationParams(**self.params_dict)
            calc = LossCalculator(params)
            matcher = ProductMatcher(self.db)
            comm_svc = CommissionService(self.db)

            results = []
            total = len(self.rows)

            for i, row in enumerate(self.rows):
                self.progress.emit(i + 1, total)
                result = self._calc_row(calc, matcher, comm_svc, row)
                results.append(result)

            self.finished.emit(results)
        except Exception as e:
            logger.exception("CalculateWorker error")
            self.error.emit(str(e))

    def _calc_row(self, calc, matcher, comm_svc, row):
        """计算单行"""
        try:
            current_price = float(str(row.current_price).replace(",", "").strip())
        except (ValueError, TypeError):
            return self._empty_row(row, "价格无效")

        product = matcher.match_product(row.seller_sku)
        if not product:
            return self._empty_row(row, "产品未匹配")

        product_cost = product.distribution_price
        # 分销价格来自飞书，已是RUB，无需转换。

        category = product.category or row.category
        comm_rate, matched, source = comm_svc.find_commission_rate(category)

        params = CalculationParams(**self.params_dict)
        params.commission_rate = comm_rate
        calc_instance = LossCalculator(params)

        l, w, h = LossCalculator.parse_dimensions(product.dimensions or "")
        if l == 0 and w == 0 and h == 0:
            l, w, h = 30, 20, 10

        discount = row.current_discount or 0
        discounted_price = current_price * (1 - discount / 100) if discount else current_price

        calc_result = calc_instance.calc_full_result(
            discounted_price, product_cost, l, w, h
        )

        _COMMISSION_SOURCE_MAP = {
            "product": "商品级",
            "category": "品类级",
            "default": "未匹配(默认30%)",
        }

        return {
            "seller_sku": row.seller_sku,
            "category": product.category or row.category,
            "current_price": current_price,
            "current_discount": discount,
            "discounted_price": round(discounted_price, 2),
            "product_cost": round(product_cost, 2),
            "commission_rate": comm_rate,
            "breakeven": round(calc_result.breakeven, 2),
            "profit": round(calc_result.current_profit, 2),
            "max_discount": calc_result.max_discount,
            "min_price": round(calc_result.min_price, 2),
            "cost_matched": True,
            "distribution_price": round(product_cost, 2),
            "shipping_fee": round(calc_result.shipping_fee, 2),
            "commission_source": _COMMISSION_SOURCE_MAP.get(source, source),
            "inventory": product.inventory,
            "row_number": row.row_number,
            "_calc_result": calc_result,
        }

    def _empty_row(self, row, reason):
        return {
            "seller_sku": row.seller_sku,
            "category": row.category,
            "current_price": row.current_price,
            "current_discount": row.current_discount or 0,
            "discounted_price": None,
            "product_cost": None,
            "commission_rate": None,
            "breakeven": None,
            "profit": None,
            "max_discount": None,
            "min_price": None,
            "cost_matched": False,
            "distribution_price": None,
            "shipping_fee": None,
            "commission_source": None,
            "inventory": None,
            "row_number": row.row_number,
            "_calc_result": None,
        }


class MainWindow(QMainWindow):
    """主窗口 — 侧边栏导航 + 顶栏 + QStackedWidget"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(get_version_text())
        self.resize(1400, 900)
        self.setMinimumSize(960, 600)

        # 数据库
        self.db = DatabaseManager()

        # 参数
        self._params = self._load_params()

        # 计算状态
        self._calc_results = []
        self._calc_worker = None

        # 构建 UI
        self._build_ui()
        self._build_statusbar()

    def _load_params(self) -> dict:
        params = dict(Config.DEFAULT_PARAMS)
        try:
            saved = self.db.get_all_config()
            for key in params:
                if key in saved:
                    try:
                        params[key] = float(saved[key])
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass
        return params

    def _save_params(self):
        for key, value in self._params.items():
            self.db.save_config(key, str(value))

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top bar (极简: 只有标题) ──
        self.top_bar = TopBar()
        root_layout.addWidget(self.top_bar)

        # ── Body: sidebar + stacked content ──
        body_splitter = QSplitter(Qt.Orientation.Horizontal)

        # SideBar
        self.sidebar = SideBar()
        body_splitter.addWidget(self.sidebar)

        # QStackedWidget — 5 pages
        self.stack = QStackedWidget()

        # Page 0: SyncWidget
        self.sync_widget = SyncWidget(self.db)
        self.sync_widget.sync_finished.connect(self._on_sync_finished)
        self.stack.addWidget(self.sync_widget)

        # Page 1: ProductViewer
        self.product_viewer = ProductViewer(self.db)
        self.stack.addWidget(self.product_viewer)

        # Page 2: CommissionViewer
        self.commission_viewer = CommissionViewer(self.db)
        self.stack.addWidget(self.commission_viewer)

        # Page 3: DiscountCalcWidget (策略+模式+文件+计算+结果+导出)
        self.discount_calc = DiscountCalcWidget()
        self.discount_calc.calculate_requested.connect(self._on_calculate)
        self.discount_calc.export_requested.connect(self._on_export)
        self.discount_calc.result_table.cellClicked.connect(self._on_row_clicked)
        self.stack.addWidget(self.discount_calc)

        # Page 4: Settings
        self.settings_widget = SettingsWidget(self._params, self)
        self.settings_widget.params_changed.connect(self._on_params_changed)
        self.stack.addWidget(self.settings_widget)

        body_splitter.addWidget(self.stack)

        body_splitter.setStretchFactor(0, 0)
        body_splitter.setStretchFactor(1, 1)
        body_splitter.setSizes([180, 1220])

        root_layout.addWidget(body_splitter)

        # ── Sidebar → Stack connection ──
        self.sidebar.currentChanged.connect(self._on_nav_changed)
        self.sidebar.themeToggleRequested.connect(self._on_theme_toggle)

        # ── 初始主题 ──
        _init_theme = ThemeManager().current_theme
        self.sidebar.refresh_theme(_init_theme)
        self.top_bar.refresh_theme(_init_theme)
        self.sync_widget.set_theme(_init_theme)

    def _build_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.statusbar.addPermanentWidget(self.progress_bar)

        self.status_label = QLabel("就绪")
        self.statusbar.addWidget(self.status_label)

        # 右下角版本号
        version_label = QLabel(get_app_version())
        version_label.setStyleSheet("color: #80868B; font-size: 11px; padding-right: 8px;")
        self.statusbar.addPermanentWidget(version_label)

    # ── Navigation ────────────────────────────

    def _on_nav_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        try:
            if index == PAGE_PRODUCTS and not self.product_viewer._loaded:
                self.product_viewer.load_data()
            elif index == PAGE_COMMISSIONS and not self.commission_viewer._loaded:
                self.commission_viewer.load_data()
        except Exception as e:
            logger.error(f"Failed to load page {index}: {e}")
            self.status_label.setText(f"加载页面失败: {e}")

    # ── Sync finished ─────────────────────────

    def _on_sync_finished(self):
        """数据同步完成后刷新各页面"""
        if self.product_viewer._loaded:
            self.product_viewer.refresh()
        if self.commission_viewer._loaded:
            self.commission_viewer.refresh()

    # ── Theme ─────────────────────────────────

    def _on_theme_toggle(self):
        try:
            tm = ThemeManager()
            app = QApplication.instance()
            if app is None:
                return
            tm.toggle_and_apply(app)
            theme = tm.current_theme
            self.sidebar.refresh_theme(theme)
            self.top_bar.refresh_theme(theme)
            self.sync_widget.set_theme(theme)
            self.status_label.setText(f"已切换至{'深色' if theme == 'dark' else '浅色'}主题")
        except Exception as e:
            logger.error(f"Theme toggle failed: {e}")

    # ── Settings ──────────────────────────────

    def _on_params_changed(self, new_params: dict):
        self._params = new_params
        self._save_params()
        self.status_label.setText("参数已保存成功")
        QMessageBox.information(self, "保存成功", "参数配置已保存")

    # ── Calculate ─────────────────────────────

    def _on_calculate(self, file_path: str, strategy: str, mode: str):
        if self._calc_worker and self._calc_worker.isRunning():
            return

        try:
            svc = ExcelService()
            rows = svc.read_template(file_path)
            self.discount_calc.set_rows(rows)
        except Exception as e:
            QMessageBox.warning(self, "读取失败", f"无法读取Excel:\n{e}")
            return

        if not rows:
            QMessageBox.information(self, "提示", "Excel文件中没有数据行")
            return

        cny_to_rub = 0.0
        if mode == DiscountCalcWidget.MODE_CROSS_BORDER:
            ex_svc = ExchangeRateService(self.db)
            cny_to_rub = ex_svc.get_cny_to_rub()
            if cny_to_rub <= 0:
                QMessageBox.warning(self, "提示",
                    "跨境模式需要汇率数据，请先同步汇率")
                return

        self._calc_results = []
        self.discount_calc.result_table.clear_results()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(rows))
        self.progress_bar.setValue(0)
        self.status_label.setText(f"正在计算 {len(rows)} 行...")

        self._calc_worker = CalculateWorker(
            rows, self._params, self.db, strategy, mode, cny_to_rub
        )
        self._calc_worker.progress.connect(self._on_calc_progress)
        self._calc_worker.finished.connect(self._on_calc_done)
        self._calc_worker.error.connect(self._on_calc_error)
        self._calc_worker.start()

    def _on_calc_progress(self, current, total):
        self.progress_bar.setValue(current)
        self.status_label.setText(f"计算中 {current}/{total}...")

    def _on_calc_done(self, results):
        self._calc_results = results
        self.discount_calc.result_table.load_results(results)
        self.progress_bar.setVisible(False)

        profit = sum(1 for r in results if r.get("profit") is not None and r["profit"] > 0)
        loss = sum(1 for r in results if r.get("profit") is not None and r["profit"] < 0)
        unmatched = sum(1 for r in results if r.get("profit") is None)

        self.discount_calc.set_export_enabled(True)
        self.discount_calc.update_summary(profit, loss, unmatched, len(results))
        self.status_label.setText(
            f"计算完成: 盈利{profit} / 亏损{loss} / 未匹配{unmatched} / 总计{len(results)}"
        )

    def _on_calc_error(self, err):
        self.progress_bar.setVisible(False)
        self.status_label.setText("计算失败")
        QMessageBox.warning(self, "计算失败", f"计算过程出错:\n{err}")

    # ── Row click detail ──────────────────────

    def _on_row_clicked(self, row: int, col: int):
        if 0 <= row < len(self._calc_results):
            from src.ui.calc_detail_dialog import CalcDetailDialog
            dlg = CalcDetailDialog(self._calc_results[row], self._params, self)
            dlg.exec()

    # ── Export ────────────────────────────────

    def _on_export(self):
        if not self._calc_results:
            QMessageBox.information(self, "提示", "没有可导出的结果")
            return

        file_path = self.discount_calc.get_file_path()
        if not file_path:
            QMessageBox.information(self, "提示", "请先选择并计算Excel文件")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出结果",
            os.path.splitext(file_path)[0] + "_结果.xlsx",
            "Excel文件 (*.xlsx)"
        )
        if not save_path:
            return

        try:
            strategy = self.discount_calc.get_strategy()
            discount_updates = {}
            price_updates = {}

            for r in self._calc_results:
                row_num = r.get("row_number")
                if not row_num:
                    continue
                calc = r.get("_calc_result")
                if not calc:
                    continue

                profit = r.get("profit", 0)
                if profit is None:
                    continue

                if strategy in (DiscountCalcWidget.STRATEGY_DISCOUNT_ONLY, DiscountCalcWidget.STRATEGY_BOTH):
                    if profit < 0 and calc.max_discount is not None:
                        discount_updates[row_num] = calc.max_discount

                if strategy in (DiscountCalcWidget.STRATEGY_PRICE_ONLY, DiscountCalcWidget.STRATEGY_BOTH):
                    if profit < 0 and calc.min_price is not None:
                        price_updates[row_num] = calc.min_price

            svc = ExcelService()
            svc.write_updates(file_path, save_path, discount_updates, price_updates)
            self.status_label.setText(f"已导出: {save_path}")
            QMessageBox.information(self, "导出成功",
                f"结果已保存到:\n{save_path}\n\n"
                f"折扣更新: {len(discount_updates)} 行\n"
                f"价格更新: {len(price_updates)} 行")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", f"导出出错:\n{e}")


class SettingsWidget(QWidget):
    """内嵌设置面板（从 SettingsDialog 改造，用于 QStackedWidget 页面）"""

    params_changed = Signal(dict)

    def __init__(self, current_params: dict, parent=None):
        super().__init__(parent)
        self._spinboxes = {}
        self._build_ui(current_params)

    def _build_ui(self, current_params: dict):
        from PySide6.QtWidgets import (
            QFormLayout, QGroupBox, QDoubleSpinBox, QPushButton,
            QScrollArea, QFrame
        )

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 16, 20, 16)

        # ── 成本参数卡片 ──
        cost_group = QGroupBox("成本参数")
        cost_group.setObjectName("settingsCard")
        cost_form = QFormLayout()
        cost_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        cost_form.setSpacing(10)
        for key, label, suffix, decimals, lo, hi, step in SettingsDialog.COST_PARAMS:
            sb = self._make_spinbox(decimals, lo, hi, step, suffix)
            sb.setValue(current_params.get(key, Config.DEFAULT_PARAMS.get(key, 0)))
            self._spinboxes[key] = sb
            cost_form.addRow(label + ":", sb)
        cost_group.setLayout(cost_form)
        layout.addWidget(cost_group)

        btn_save_cost = QPushButton("保存成本参数")
        btn_save_cost.setProperty("class", "btn-primary")
        btn_save_cost.setMinimumHeight(36)
        btn_save_cost.clicked.connect(self._on_save)
        layout.addWidget(btn_save_cost)

        # ── 费率参数卡片 ──
        rate_group = QGroupBox("费率参数")
        rate_group.setObjectName("settingsCard")
        rate_form = QFormLayout()
        rate_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        rate_form.setSpacing(10)
        for key, label, suffix, decimals, lo, hi, step in SettingsDialog.RATE_PARAMS:
            sb = self._make_spinbox(decimals, lo, hi, step, suffix)
            sb.setValue(current_params.get(key, Config.DEFAULT_PARAMS.get(key, 0)))
            self._spinboxes[key] = sb
            rate_form.addRow(label + ":", sb)
        rate_group.setLayout(rate_form)
        layout.addWidget(rate_group)

        btn_save_rate = QPushButton("保存费率参数")
        btn_save_rate.setProperty("class", "btn-primary")
        btn_save_rate.setMinimumHeight(36)
        btn_save_rate.clicked.connect(self._on_save)
        layout.addWidget(btn_save_rate)

        layout.addStretch()

        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _make_spinbox(self, decimals, lo, hi, step, suffix):
        from PySide6.QtWidgets import QDoubleSpinBox
        sb = QDoubleSpinBox()
        sb.setDecimals(decimals)
        sb.setRange(lo, hi)
        sb.setSingleStep(step)
        if suffix:
            sb.setSuffix(suffix)
        return sb

    def _on_save(self):
        params = {key: sb.value() for key, sb in self._spinboxes.items()}
        self.params_changed.emit(params)
