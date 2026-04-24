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
from src.services.excel_service import ExcelService
from src.services.discount_calc_svc import DiscountCalcService
from src.services.exchange_rate import ExchangeRateService
from src.services.shipping_service import ShippingService

from src.ui.sidebar import SideBar
from src.ui.top_bar import TopBar
from src.ui.sync_widget import SyncWidget
from src.ui.data_viewers import ProductViewer, CommissionViewer
from src.ui.discount_calc_widget import DiscountCalcWidget
from src.ui.settings_dialog import SettingsDialog
from src.ui.theme_manager import ThemeManager
from src.ui.interfaces.registry import InterfaceRegistry
from src.services.calculator import LossCalculator
from src.version import get_app_version, get_version_text

logger = logging.getLogger(__name__)

# Page indices in QStackedWidget
PAGE_SYNC = 0
PAGE_PRODUCTS = 1
PAGE_COMMISSIONS = 2
PAGE_DISCOUNT_CALC = 3
PAGE_SETTINGS = 4


class _CalculateWorker(QThread):
    """Step 2 worker: Calculate profit/discount from matched results."""
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, svc, params_dict, exchange_rate):
        super().__init__()
        self.svc = svc
        self.params_dict = params_dict
        self.exchange_rate = exchange_rate

    def run(self):
        try:
            count = self.svc.calculate_from_match(self.params_dict, self.exchange_rate)
            if not self.isInterruptionRequested():
                self.finished.emit(count)
        except Exception as e:
            if not self.isInterruptionRequested():
                logger.exception("_CalculateWorker error")
                self.error.emit(str(e))


class MainWindow(QMainWindow):
    """主窗口 — 侧边栏导航 + 顶栏 + QStackedWidget"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(get_version_text())
        self.resize(1400, 900)
        self.setMinimumSize(960, 600)

        # 数据库 — 按模块独立
        self._app_db = DatabaseManager(Config.DB_APP_PATH, init_tables=["app_config"])
        self._feishu_db = DatabaseManager(Config.DB_FEISHU_PATH, init_tables=["products", "app_config"])
        self._commission_db = DatabaseManager(Config.DB_COMMISSION_PATH, init_tables=["commissions", "commission_meta", "app_config"])
        self._exchange_rate_db = DatabaseManager(Config.DB_EXCHANGE_RATE_PATH, init_tables=["exchange_rates", "app_config"])
        self._discount_calc_db = DatabaseManager(Config.DB_DISCOUNT_CALC_PATH,
                                                  init_tables=["import_rows", "calc_results", "app_config"])

        # 运费服务
        self._shipping_svc = ShippingService()

        # 折扣推算服务 (连接所有需要的DB + 运费服务)
        self._discount_svc = DiscountCalcService(
            db=self._discount_calc_db,
            feishu_db=self._feishu_db,
            commission_db=self._commission_db,
            shipping_svc=self._shipping_svc,
        )

        # 参数
        self._params = self._load_params()

        # 计算状态
        self._calc_results = []
        self._calc_worker = None

        # 构建 UI
        self._build_ui()
        self._build_statusbar()

    def closeEvent(self, event):
        """Clean up all workers and force application exit."""
        logger.info("MainWindow closing...")

        # 1. Stop CalcWorker (owned by MainWindow)
        if self._calc_worker and self._calc_worker.isRunning():
            self._calc_worker.requestInterruption()
            self._calc_worker.quit()
            self._calc_worker.wait(3000)
            if self._calc_worker.isRunning():
                self._calc_worker.terminate()
                self._calc_worker.wait(1000)

        # 2. Stop all interface module workers (feishu, commission, exchange_rate)
        try:
            self.sync_widget.stop_all_workers()
        except Exception:
            pass

        # 3. Shutdown debug log manager completely (closes window + removes handlers)
        try:
            from src.ui.debug_log_window import DebugLogManager
            mgr = DebugLogManager()
            if mgr:
                mgr.shutdown()
        except Exception:
            pass

        # 4. Close ALL top-level windows (not just visible ones)
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                if widget is not self:
                    try:
                        widget.close()
                    except Exception:
                        pass

        # 5. Force quit the application
        if app:
            app.quit()

        event.accept()

    def _load_params(self) -> dict:
        params = dict(Config.DEFAULT_PARAMS)
        try:
            saved = self._app_db.get_all_config()
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
            self._app_db.save_config(key, str(value))

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

        # Page 0: SyncWidget（传入 app_db 用于接口启用/禁用状态管理）
        self.sync_widget = SyncWidget(self._app_db)
        self.sync_widget.sync_finished.connect(self._on_sync_finished)
        self.stack.addWidget(self.sync_widget)

        # Page 1: ProductViewer（读取飞书DB的产品数据）
        self.product_viewer = ProductViewer(self._feishu_db)
        self.stack.addWidget(self.product_viewer)

        # Page 2: CommissionViewer（读取佣金DB的佣金数据）
        self.commission_viewer = CommissionViewer(self._commission_db)
        self.stack.addWidget(self.commission_viewer)

        # Page 3: DiscountCalcWidget (佣金表+策略+文件导入+计算+结果+导出)
        self.discount_calc = DiscountCalcWidget()
        self.discount_calc.set_service(self._discount_svc)
        self.discount_calc.calculate_requested.connect(self._on_calculate_requested)
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

        # ── 根据模块启用状态控制导航可见性 ──
        self._update_nav_visibility()

    def _update_nav_visibility(self):
        """根据模块启用状态控制导航项可见性"""
        try:
            registry = InterfaceRegistry()
            # 产品数据页(PAGE_PRODUCTS=1) 依赖飞书模块
            feishu_enabled = registry.is_enabled(self._app_db, "feishu")
            self.sidebar.set_nav_visible(PAGE_PRODUCTS, feishu_enabled)
        except Exception:
            pass

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
        version_label.setProperty("class", "stat-label")
        self.statusbar.addPermanentWidget(version_label)

    # ── Navigation ────────────────────────────

    def _on_nav_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        try:
            if index == PAGE_PRODUCTS and not self.product_viewer._loaded:
                self.product_viewer.load_data()
            elif index == PAGE_COMMISSIONS and not self.commission_viewer._loaded:
                self.commission_viewer.load_data()
            elif index == PAGE_DISCOUNT_CALC:
                pass  # Commission tables loaded in import dialog
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
            # 通知 debug 日志窗口
            try:
                from src.ui.debug_log_window import DebugLogManager
                DebugLogManager().set_theme(theme == "dark")
            except Exception:
                pass
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

    def _on_calculate_requested(self):
        """Dispatch to match or calculate based on current state."""
        if self._calc_worker and self._calc_worker.isRunning():
            return

        if self._discount_calc_db.get_import_row_count() == 0:
            QMessageBox.information(self, "提示", "请先导入Excel文件")
            return

        if not self.discount_calc.is_matched():
            self._on_match()
        else:
            self._on_calculate()

    def _on_match(self):
        """Step 1: Match SKU + commission + calculate shipping."""
        commission_table = self.discount_calc.get_commission_table()
        try:
            count = self._discount_svc.match(commission_table)
            self.discount_calc.set_match_result(count)
            # Populate match tab
            combined = self._discount_svc.get_import_data()
            match_data = self._build_match_display(combined)
            self.discount_calc.match_table.populate(match_data)
            self.discount_calc.tabs.setCurrentIndex(1)  # Switch to match data tab
            self.status_label.setText(f"匹配完成: {count} 条")
        except Exception as e:
            logger.exception("Match error")
            QMessageBox.warning(self, "匹配失败", str(e))
            self.discount_calc.set_match_result(0)
            self.status_label.setText("匹配失败")

    def _on_calculate(self):
        """Step 2: Calculate profit/discount from matched results."""
        rate = self.discount_calc.get_exchange_rate()
        self._calc_results = []
        self.discount_calc.result_table.clear_results()
        self.status_label.setText("正在计算...")

        self._calc_worker = _CalculateWorker(
            self._discount_svc, self._params, rate)
        self._calc_worker.finished.connect(self._on_calc_done)
        self._calc_worker.error.connect(self._on_calc_error)
        self._calc_worker.start()

    def _on_calc_done(self, count):
        self.discount_calc.progress.setVisible(False)

        # Load results from DB and display
        combined = self._discount_svc.get_import_data()
        results = self._build_display_results(combined)
        self._calc_results = results
        self.discount_calc.result_table.load_results(results)

        # Populate match and calc tables
        match_data = self._build_match_display(combined)
        calc_data = self._build_calc_display(combined)
        self.discount_calc.match_table.populate(match_data)
        self.discount_calc.calc_table.populate(calc_data)

        summary = self._discount_svc.get_summary()
        self.discount_calc.update_summary(summary)
        self.discount_calc.set_export_enabled(count > 0)
        self.discount_calc.tabs.setCurrentIndex(3)  # Switch to 结果数据 tab
        self.status_label.setText(
            f"计算完成: 盈利{summary['profit']} / 亏损{summary['loss']} / "
            f"未匹配{summary['unmatched']} / 总计{summary['total']}"
        )

    def _on_calc_error(self, err):
        self.discount_calc.progress.setVisible(False)
        self.status_label.setText("计算失败")
        QMessageBox.warning(self, "计算失败", f"计算过程出错:\n{err}")

    def _build_display_results(self, combined_data) -> list:
        """Convert (import_row, calc_result) tuples to display dicts for ResultTable.

        DB column indices (verified against CREATE TABLE):
        import_rows: (0=id, 1=row_number, 2=brand, 3=category, 4=wb_article,
                      5=seller_sku, 6=barcode, 7=wb_stock, 8=seller_stock,
                      9=turnover, 10=current_price, 11=new_price,
                      12=current_discount, 13=new_discount, 14=import_batch)
        calc_results: (0=id, 1=import_row_id, 2=sku_matched, 3=category_matched,
                        4=matched_product_id, 5=product_cost, 6=product_category,
                        7=dimensions, 8=weight,
                        9=inventory, 10=inventory_status,
                        11=seller_stock, 12=wb_stock,
                        13=commission_rate, 14=commission_source,
                        15=discounted_price, 16=shipping_fee,
                        17=breakeven, 18=profit, 19=max_discount, 20=min_price,
                        21=target_discount, 22=target_price,
                        23=calc_batch)
        """
        results = []
        for imp, calc in combined_data:
            if calc is None:
                results.append({
                    "seller_sku": imp[5] or "",
                    "category": imp[3] or "",
                    "current_price": imp[10] or "",
                    "current_discount": imp[12] or 0,
                    "discounted_price": None,
                    "distribution_price": None,
                    "shipping_fee": None,
                    "seller_stock": str(imp[8] or ""),
                    "wb_stock": str(imp[7] or ""),
                    "inventory_status": "",
                    "cost_matched": False,
                    "commission_source": "未计算",
                    "product_cost": None,
                    "commission_rate": None,
                    "breakeven": None,
                    "profit": None,
                    "max_discount": None,
                    "target_discount": None,
                    "min_price": None,
                    "target_price": None,
                    "row_number": imp[1] or 0,
                    "_calc_result": None,
                })
            else:
                sku_ok = bool(calc[2])   # sku_matched
                cat_ok = bool(calc[3])   # category_matched
                # Build commission_source with both match statuses
                if not sku_ok:
                    comm_src = "产品未匹配"
                else:
                    comm_src = calc[14] or ""  # commission_source
                    if cat_ok:
                        comm_src += " ✅"
                    else:
                        comm_src = "❌类目 " + comm_src

                results.append({
                    "seller_sku": imp[5] or "",
                    "category": calc[6] or imp[3] or "",  # product_category or raw category
                    "current_price": imp[10] or "",
                    "current_discount": imp[12] or 0,
                    "discounted_price": calc[15],  # discounted_price
                    "distribution_price": calc[5],  # product_cost
                    "shipping_fee": calc[16],       # shipping_fee
                    "seller_stock": calc[11] or str(imp[8] or ""),  # seller_stock from calc or import
                    "wb_stock": calc[12] or str(imp[7] or ""),      # wb_stock from calc or import
                    "inventory_status": calc[10],    # inventory_status
                    "cost_matched": sku_ok,
                    "category_matched": cat_ok,
                    "commission_source": comm_src,
                    "product_cost": calc[5],        # product_cost
                    "commission_rate": calc[13],    # commission_rate
                    "breakeven": calc[17],          # breakeven
                    "profit": calc[18],             # profit
                    "max_discount": calc[19],       # max_discount
                    "target_discount": calc[21],    # target_discount
                    "min_price": calc[20],          # min_price
                    "target_price": calc[22],       # target_price
                    "row_number": imp[1] or 0,
                    "_calc_result": None,
                })
        return results

    def _build_match_display(self, combined_data) -> list:
        """Build display data for MatchDataTable.

        Extracts matching intermediate results: SKU match, commission match,
        inventory status, product cost, volume, etc.
        """
        results = []
        for imp, calc in combined_data:
            if calc is None:
                results.append({
                    "row_number": imp[1] or 0,
                    "seller_sku": imp[5] or "",
                    "category": imp[3] or "",
                    "sku_matched": False,
                    "matched_product_id": "-",
                    "product_category": "-",
                    "dimensions": "-",
                    "wb_stock": str(imp[7] or ""),
                    "seller_stock": str(imp[8] or ""),
                    "inventory_status": "-",
                    "commission_rate": None,
                    "category_matched": False,
                    "product_cost": None,
                    "density": None,
                    "weight": None,
                })
            else:
                sku_ok = bool(calc[2])   # sku_matched
                cat_ok = bool(calc[3])   # category_matched
                dim_str = calc[7] or ""   # dimensions
                # Calculate density from dimensions and weight
                weight_kg = calc[8]  # weight from calc_results (may be None)
                volume_l = None
                if dim_str and dim_str != "-":
                    try:
                        l, w, h = LossCalculator.parse_dimensions(str(dim_str))
                        if l and w and h:
                            volume_l = l * w * h / 1000
                    except Exception:
                        pass
                # Density = weight_kg / volume_l
                density = None
                if weight_kg and weight_kg > 0 and volume_l and volume_l > 0:
                    density = weight_kg / volume_l

                results.append({
                    "row_number": imp[1] or 0,
                    "seller_sku": imp[5] or "",
                    "category": calc[6] or imp[3] or "",
                    "sku_matched": sku_ok,
                    "matched_product_id": calc[4] or "-",
                    "product_category": calc[6] or "-",
                    "dimensions": dim_str or "-",
                    "wb_stock": str(imp[7] or ""),
                    "seller_stock": str(imp[8] or ""),
                    "inventory_status": calc[10] or "-",
                    "commission_rate": calc[13],
                    "category_matched": cat_ok,
                    "product_cost": calc[5],
                    "density": density,
                    "weight": weight_kg,
                })
        return results

    def _build_calc_display(self, combined_data) -> list:
        """Build display data for CalcDataTable.

        Extracts detailed calculation breakdown: prices, fees, breakeven, profit, etc.
        """
        results = []
        for imp, calc in combined_data:
            if calc is None:
                results.append({
                    "row_number": imp[1] or 0,
                    "seller_sku": imp[5] or "",
                    "current_price": imp[10] or "",
                    "discounted_price": None,
                    "product_cost": None,
                    "shipping_fee": None,
                    "breakeven": None,
                    "profit": None,
                    "max_discount": None,
                    "target_discount": None,
                    "min_price": None,
                    "target_price": None,
                })
            else:
                results.append({
                    "row_number": imp[1] or 0,
                    "seller_sku": imp[5] or "",
                    "current_price": imp[10] or "",
                    "discounted_price": calc[15],   # discounted_price
                    "product_cost": calc[5],        # product_cost
                    "shipping_fee": calc[16],       # shipping_fee
                    "breakeven": calc[17],          # breakeven
                    "profit": calc[18],             # profit
                    "max_discount": calc[19],       # max_discount
                    "target_discount": calc[21],    # target_discount
                    "min_price": calc[20],          # min_price
                    "target_price": calc[22],       # target_price
                })
        return results

    # ── Row click detail ──────────────────────

    def _on_row_clicked(self, row: int, col: int):
        if 0 <= row < len(self._calc_results):
            from src.ui.calc_detail_dialog import CalcDetailDialog
            dlg = CalcDetailDialog(self._calc_results[row], self._params, self)
            dlg.exec()

    # ── Export ────────────────────────────────

    def _on_export(self):
        combined = self._discount_svc.get_import_data()
        if not combined or all(calc is None for _, calc in combined):
            QMessageBox.information(self, "提示", "没有可导出的结果")
            return

        file_path = self.discount_calc.get_file_path()
        if not file_path:
            QMessageBox.information(self, "提示", "请先导入并计算Excel文件")
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

            for imp, calc in combined:
                if calc is None:
                    continue
                row_num = imp[1]  # row_number
                if not row_num:
                    continue
                profit = calc[18]  # profit
                if profit is None:
                    continue
                max_discount = calc[19]  # max_discount
                min_price = calc[20]    # min_price

                if strategy in (DiscountCalcWidget.STRATEGY_DISCOUNT_ONLY, DiscountCalcWidget.STRATEGY_BOTH):
                    if profit < 0 and max_discount is not None:
                        discount_updates[row_num] = max_discount

                if strategy in (DiscountCalcWidget.STRATEGY_PRICE_ONLY, DiscountCalcWidget.STRATEGY_BOTH):
                    if profit < 0 and min_price is not None:
                        price_updates[row_num] = min_price

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
