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

PAGE_CONTEXT = {
    PAGE_SYNC: ("数据接口", "同步产品、佣金、汇率等基础数据，保证测算输入可靠。", "接口管理", "检查连接状态与同步结果"),
    PAGE_PRODUCTS: ("产品资料", "查看飞书同步下来的产品资料、尺寸、库存与原始字段。", "产品数据", "核对 SKU、类目、库存状态"),
    PAGE_COMMISSIONS: ("佣金资料", "维护 Wildberries 佣金表，为后续盈亏测算提供费率基础。", "佣金数据", "确认类目映射与默认佣金"),
    PAGE_DISCOUNT_CALC: ("折扣测算", "完成导入、匹配、盈亏测算与结果导出，是运营日常的主工作区。", "核心流程", "建议按 步骤1 匹配 -> 步骤2 计算 执行"),
    PAGE_SETTINGS: ("参数设置", "维护成本项、风险项与目标利润参数，统一团队测算口径。", "参数中心", "修改后将影响后续所有新计算"),
}


class _CalculateWorker(QThread):
    """Step 2 worker: Calculate profit/discount from matched results."""
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, svc, params_dict, exchange_rate=1.0):
        super().__init__()
        self.svc = svc
        self.params_dict = params_dict
        self.exchange_rate = exchange_rate

    def run(self):
        try:
            count = self.svc.calculate_from_match(self.params_dict, exchange_rate=self.exchange_rate)
            if not self.isInterruptionRequested():
                self.finished.emit(count)
        except Exception as e:
            if not self.isInterruptionRequested():
                logger.exception("_CalculateWorker error")
                self.error.emit(str(e))


class _ImportWorker(QThread):
    """Async worker for Excel import so large files do not block the UI."""
    finished = Signal(str, int)
    error = Signal(str)

    def __init__(self, svc, file_path: str):
        super().__init__()
        self.svc = svc
        self.file_path = file_path

    def run(self):
        try:
            count = self.svc.import_from_excel(self.file_path)
            if not self.isInterruptionRequested():
                self.finished.emit(self.file_path, count)
        except Exception as e:
            if not self.isInterruptionRequested():
                logger.exception("_ImportWorker error")
                self.error.emit(str(e))


class _MatchWorker(QThread):
    """Step 1 worker: Match SKU + commission + calculate shipping."""
    finished = Signal(int)
    error = Signal(str)
    progress = Signal(int, int)  # (total, current)

    def __init__(self, svc, commission_table, exchange_rate=1.0):
        super().__init__()
        self.svc = svc
        self.commission_table = commission_table
        self.exchange_rate = exchange_rate

    def run(self):
        try:
            count = self.svc.match(
                self.commission_table,
                exchange_rate=self.exchange_rate,
                progress_callback=lambda t, c: self.progress.emit(t, c),
                should_stop=lambda: self.isInterruptionRequested(),
            )
            if not self.isInterruptionRequested():
                self.finished.emit(count)
        except Exception as e:
            if not self.isInterruptionRequested():
                logger.exception("_MatchWorker error")
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
        self._import_worker = None
        self._match_worker = None

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

        # 2. Stop ImportWorker
        if self._import_worker and self._import_worker.isRunning():
            self._import_worker.requestInterruption()
            self._import_worker.quit()
            self._import_worker.wait(3000)
            if self._import_worker.isRunning():
                self._import_worker.terminate()
                self._import_worker.wait(1000)

        # 3. Stop MatchWorker
        if self._match_worker and self._match_worker.isRunning():
            self._match_worker.requestInterruption()
            self._match_worker.quit()
            self._match_worker.wait(3000)
            if self._match_worker.isRunning():
                self._match_worker.terminate()
                self._match_worker.wait(1000)

        # 4. Stop all interface module workers (feishu, commission, exchange_rate)
        try:
            self.sync_widget.stop_all_workers()
        except Exception:
            pass

        # 5. Shutdown debug log manager completely (closes window + removes handlers)
        try:
            from src.ui.debug_log_window import DebugLogManager
            mgr = DebugLogManager()
            if mgr:
                mgr.shutdown()
        except Exception:
            pass

        # 6. Close ALL top-level windows (not just visible ones)
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                if widget is not self:
                    try:
                        widget.close()
                    except Exception:
                        pass

        # 7. Force quit the application
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
        self.discount_calc.import_requested.connect(self._on_import_requested)
        self.discount_calc.export_requested.connect(self._on_export)
        self.discount_calc.result_table.doubleClicked.connect(self._on_result_copy_cell)
        self.discount_calc.calc_table.view_clicked.connect(self._on_calc_view_clicked)
        self.discount_calc.import_done.connect(self._on_import_done)
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
        self._set_page_context(PAGE_SYNC)

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
        self._set_page_context(index)
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

    def _set_page_context(self, index: int):
        title, subtitle, badge, hint = PAGE_CONTEXT.get(
            index,
            ("店铺运营工作台", "围绕导入、匹配、测算、导出的一体化运营流程", "当前模块", "准备开始"),
        )
        self.top_bar.set_context(title, subtitle, badge, hint)

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
        if self._import_worker and self._import_worker.isRunning():
            return
        if self._calc_worker and self._calc_worker.isRunning():
            return
        if self._match_worker and self._match_worker.isRunning():
            return

        if self._discount_calc_db.get_import_row_count() == 0:
            QMessageBox.information(self, "提示", "请先导入Excel文件")
            return

        if not self.discount_calc.is_matched():
            self._on_match()
        else:
            self._on_calculate()

    def _on_import_requested(self, file_path: str):
        """Import the selected Excel file in the background."""
        if self._import_worker and self._import_worker.isRunning():
            return
        self.status_label.setText("正在导入 Excel...")
        self._import_worker = _ImportWorker(self._discount_svc, file_path)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.start()

    def _on_import_finished(self, file_path: str, count: int):
        self.discount_calc.set_import_result(file_path, count)
        self.status_label.setText(f"导入完成: {count} 行")

    def _on_import_error(self, err: str):
        self.discount_calc.set_import_error(err)
        self.status_label.setText("导入失败")

    def _on_match(self):
        """Step 1: Match SKU + commission + calculate shipping.
        Uses shop_type and exchange_rate already configured in DiscountCalcWidget.
        """
        commission_table = self.discount_calc.get_commission_table()
        exchange_rate = self.discount_calc.get_exchange_rate()
        self.status_label.setText("正在匹配...")

        self._match_worker = _MatchWorker(self._discount_svc, commission_table, exchange_rate)
        self._match_worker.finished.connect(self._on_match_done)
        self._match_worker.error.connect(self._on_match_error)
        self._match_worker.progress.connect(self._on_match_progress)
        self._match_worker.start()

    def _on_match_done(self, count):
        self.discount_calc.set_match_result(count)
        try:
            combined = self._discount_svc.get_import_data()
            tables = self.discount_calc

            # 更新匹配表（全量更新）
            match_data = self._build_match_display(combined)
            tables.match_table.populate(match_data)

            # 构建 calc 和 result 数据（匹配列有值，计算列保持None）
            calc_data = self._build_calc_display(combined)
            result_data = self._build_display_results(combined)

            # 计算表：populate 全量填充（重建查看按钮）
            tables.calc_table.populate(calc_data)

            # 结果表：populate 全量填充
            tables.result_table.load_results(result_data)

            # 更新 _calc_results（查看按钮用）
            self._calc_results = result_data
        except Exception:
            logger.exception("Failed to display match results")
        self.discount_calc.tabs.setCurrentIndex(1)  # Switch to match data tab
        self.status_label.setText(f"匹配完成: {count} 条")

    def _on_match_error(self, err):
        self.discount_calc.set_match_result(0)
        self.discount_calc.progress.setVisible(False)
        self.status_label.setText("匹配失败")
        QMessageBox.warning(self, "匹配失败", str(err))

    def _on_match_progress(self, total, current):
        bar = self.discount_calc.progress
        if total > 0:
            bar.setRange(0, total)
            bar.setValue(current)
            bar.setVisible(True)

    def _on_calculate(self):
        """Step 2: Calculate profit/discount from matched results."""
        self._calc_results = []
        self.discount_calc.result_table.clear_results()
        self.status_label.setText("正在计算...")

        exchange_rate = self.discount_calc.get_exchange_rate()
        self._calc_worker = _CalculateWorker(
            self._discount_svc, self._params, exchange_rate)
        self._calc_worker.finished.connect(self._on_calc_done)
        self._calc_worker.error.connect(self._on_calc_error)
        self._calc_worker.start()

    def _on_calc_done(self, count):
        self.discount_calc.set_calc_result(count)
        combined = self._discount_svc.get_import_data()

        tables = self.discount_calc
        # 全量刷新结果表（clear_results清空了数据，不能用update_calc_columns）
        result_data = self._build_display_results(combined)
        self._calc_results = result_data
        tables.result_table.load_results(result_data)

        # 全量刷新计算表（同样需要 populate 来重建按钮）
        calc_data = self._build_calc_display(combined)
        tables.calc_table.populate(calc_data)

        summary = self._discount_svc.get_summary()
        tables.update_summary(summary)
        tables.set_export_enabled(count > 0)
        tables.tabs.setCurrentIndex(3)  # Switch to 结果数据 tab
        self.status_label.setText(
            f"计算完成: 盈利{summary['profit']} / 亏损{summary['loss']} / "
            f"未匹配{summary['unmatched']} / 总计{summary['total']}"
        )

    def _on_calc_error(self, err):
        self.discount_calc.progress.setVisible(False)
        self.discount_calc.btn_calculate.setEnabled(True)
        self.status_label.setText("计算失败")
        QMessageBox.warning(self, "计算失败", f"计算过程出错:\n{err}")

    def _on_import_done(self):
        """导入完成后填充4个表（匹配/计算列显示"-"）"""
        combined = self._discount_svc.get_import_data()
        if not combined:
            return

        self.status_label.setText("正在加载表格数据...")

        # 批量更新UI
        tables = self.discount_calc
        # 构建3个表的显示数据
        match_data = self._build_match_display(combined)
        calc_data = self._build_calc_display(combined)
        result_data = self._build_display_results(combined)

        tables.match_table.populate(match_data)

        tables.calc_table.populate(calc_data)

        tables.result_table.load_results(result_data)

        # 初始化 _calc_results（用于查看按钮/行点击）
        self._calc_results = result_data
        self.status_label.setText(f"已导入 {len(combined)} 行数据")

    def _build_display_results(self, combined_data) -> list:
        """Convert (import_row, calc_result) tuples to display dicts for ResultTable.

        DB column indices (29 columns after adding cbase/crisk/r_total/total_fixed):
        import_rows: (0=id, 1=row_number, 2=brand, 3=category, 4=wb_article,
                      5=seller_sku, 6=barcode, 7=wb_stock, 8=seller_stock,
                      9=turnover, 10=current_price, 11=new_price,
                      12=current_discount, 13=new_discount, 14=import_batch)
        calc_results: (0=id, 1=import_row_id, 2=sku_matched, 3=category_matched,
                        4=matched_product_id, 5=product_cost, 6=distribution_price,
                        7=product_category, 8=dimensions, 9=weight,
                        10=inventory, 11=inventory_status,
                        12=seller_stock, 13=wb_stock,
                        14=commission_rate, 15=commission_source,
                        16=discounted_price, 17=shipping_fee,
                        18=breakeven, 19=profit, 20=max_discount, 21=min_price,
                        22=target_discount, 23=target_price,
                        24=cbase, 25=crisk, 26=r_total, 27=total_fixed,
                        28=calc_batch)
        """
        results = []
        for imp, calc in combined_data:
            if calc is None:
                results.append({
                    "seller_sku": imp[5] or "",
                    "category": imp[3] or "",
                    "current_price": imp[10] or "",
                    "current_discount": imp[12] or 0,
                    "discounted_price": round(float(imp[10]) * (1 - float(imp[12]) / 100), 2) if imp[10] is not None and imp[12] is not None else None,
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
                    comm_src = calc[15] or ""  # commission_source
                    if cat_ok:
                        comm_src += " ✅"
                    else:
                        comm_src = "❌类目 " + comm_src

                results.append({
                    "seller_sku": imp[5] or "",
                    "category": calc[7] or imp[3] or "",  # product_category or raw category
                    "current_price": imp[10] or "",
                    "current_discount": imp[12] or 0,
                    "discounted_price": round(float(imp[10]) * (1 - float(imp[12]) / 100), 2) if imp[10] is not None and imp[12] is not None else calc[16],    # discounted_price
                    "distribution_price": calc[6],   # distribution_price (original RUB)
                    "shipping_fee": calc[17],        # shipping_fee
                    "seller_stock": calc[12] or str(imp[8] or ""),  # seller_stock from calc or import
                    "wb_stock": calc[13] or str(imp[7] or ""),      # wb_stock from calc or import
                    "inventory_status": calc[11],    # inventory_status
                    "cost_matched": sku_ok,
                    "category_matched": cat_ok,
                    "commission_source": comm_src,
                    "product_cost": calc[5],         # product_cost
                    "commission_rate": calc[14],     # commission_rate
                    "breakeven": calc[18],           # breakeven
                    "profit": calc[19],              # profit
                    "max_discount": calc[20],        # max_discount
                    "target_discount": calc[22],     # target_discount
                    "min_price": calc[21],           # min_price
                    "target_price": calc[23],        # target_price
                    "cbase": calc[24],               # cbase
                    "crisk": calc[25],               # crisk
                    "r_total": calc[26],             # r_total
                    "total_fixed": calc[27],         # total_fixed
                    "inventory": calc[10],           # inventory
                    "row_number": imp[1] or 0,
                    "_calc_result": None,
                })
        return results

    def _build_match_display(self, combined_data) -> list:
        """Build display data for MatchDataTable.

        Extracts matching intermediate results: SKU match, commission match,
        inventory status, product cost, distribution price, shipping fee, volume, etc.

        calc_results column layout (29 columns):
        (0=id, 1=import_row_id, 2=sku_matched, 3=category_matched,
         4=matched_product_id, 5=product_cost, 6=distribution_price,
         7=product_category, 8=dimensions, 9=weight,
         10=inventory, 11=inventory_status, 12=seller_stock, 13=wb_stock,
         14=commission_rate, 15=commission_source,
         16=discounted_price, 17=shipping_fee,
         18=breakeven, 19=profit, 20=max_discount, 21=min_price,
         22=target_discount, 23=target_price,
         24=cbase, 25=crisk, 26=r_total, 27=total_fixed,
         28=calc_batch)
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
                    "distribution_price": None,
                    "shipping_fee": None,
                    "volume": None,
                    "density": None,
                    "weight": None,
                })
            else:
                sku_ok = bool(calc[2])   # sku_matched
                cat_ok = bool(calc[3])   # category_matched
                dim_str = calc[8] or ""   # dimensions
                # Calculate density from dimensions and weight
                weight_kg = calc[9]  # weight from calc_results (may be None)
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
                    "category": calc[7] or imp[3] or "",
                    "sku_matched": sku_ok,
                    "matched_product_id": calc[4] or "-",
                    "product_category": calc[7] or "-",
                    "dimensions": dim_str or "-",
                    "wb_stock": str(imp[7] or ""),
                    "seller_stock": str(imp[8] or ""),
                    "inventory_status": calc[11] or "-",
                    "commission_rate": calc[14],
                    "category_matched": cat_ok,
                    "product_cost": calc[5],
                    "distribution_price": calc[6],
                    "shipping_fee": calc[17],
                    "volume": round(volume_l, 3) if volume_l else None,
                    "density": density,
                    "weight": weight_kg,
                })
        return results

    def _build_calc_display(self, combined_data) -> list:
        """Build display data for CalcDataTable.

        Extracts detailed calculation breakdown: prices, fees, breakeven, profit, etc.

        calc_results column layout (29 columns):
        (0=id, 1=import_row_id, 2=sku_matched, 3=category_matched,
         4=matched_product_id, 5=product_cost, 6=distribution_price,
         7=product_category, 8=dimensions, 9=weight,
         10=inventory, 11=inventory_status, 12=seller_stock, 13=wb_stock,
         14=commission_rate, 15=commission_source,
         16=discounted_price, 17=shipping_fee,
         18=breakeven, 19=profit, 20=max_discount, 21=min_price,
         22=target_discount, 23=target_price,
         24=cbase, 25=crisk, 26=r_total, 27=total_fixed,
         28=calc_batch)

        import_rows column layout:
        (0=id, 1=row_number, ..., 10=current_price, 11=new_price,
         12=current_discount, 13=new_discount, 14=import_batch)
        """
        results = []
        for data_idx, (imp, calc) in enumerate(combined_data):
            if calc is None:
                results.append({
                    "row_number": imp[1] or 0,
                    "seller_sku": imp[5] or "",
                    "current_price": imp[10] or "",
                    "current_discount": imp[12] or 0,
                    "discounted_price": round(float(imp[10]) * (1 - float(imp[12]) / 100), 2) if imp[10] is not None and imp[12] is not None else None,
                    "product_cost": None,
                    "shipping_fee": None,
                    "cbase": None,
                    "crisk": None,
                    "r_total": None,
                    "total_fixed": None,
                    "breakeven": None,
                    "profit": None,
                    "max_discount": None,
                    "target_discount": None,
                    "min_price": None,
                    "target_price": None,
                    "_data_index": data_idx,
                })
            else:
                results.append({
                    "row_number": imp[1] or 0,
                    "seller_sku": imp[5] or "",
                    "current_price": imp[10] or "",
                    "current_discount": imp[12] or 0,
                    "discounted_price": round(float(imp[10]) * (1 - float(imp[12]) / 100), 2) if imp[10] is not None and imp[12] is not None else calc[16],
                    "product_cost": calc[5],        # product_cost
                    "shipping_fee": calc[17],       # shipping_fee
                    "cbase": calc[24],              # cbase
                    "crisk": calc[25],              # crisk
                    "r_total": calc[26],            # r_total
                    "total_fixed": calc[27],        # total_fixed
                    "breakeven": calc[18],          # breakeven
                    "profit": calc[19],             # profit
                    "max_discount": calc[20],       # max_discount
                    "target_discount": calc[22],    # target_discount
                    "min_price": calc[21],          # min_price
                    "target_price": calc[23],       # target_price
                    "_data_index": data_idx,
                })
        return results

    # ── Row click detail ──────────────────────

    def _on_result_copy_cell(self, index):
        """双击结果表格单元格 — 复制内容到剪贴板"""
        text = index.data()
        if text and text != "-":
            QApplication.clipboard().setText(str(text))
            self.status_label.setText(f"已复制: {text}")
            # 短暂显示后恢复
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self.status_label.setText(self.status_label.text()))

    def _on_calc_view_clicked(self, data_idx: int):
        """计算数据表"查看"按钮点击 → 弹出计算详情"""
        if 0 <= data_idx < len(self._calc_results):
            from src.ui.calc_detail_dialog import CalcDetailDialog
            currency = self.discount_calc.get_currency()
            dlg = CalcDetailDialog(self._calc_results[data_idx], self._params, currency, self)
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
            negative_discount_rows = []  # 记录折扣被修正为0的行

            for imp, calc in combined:
                if calc is None:
                    continue
                row_num = imp[1]  # row_number
                if not row_num:
                    continue
                profit = calc[19]  # profit
                if profit is None:
                    continue
                target_discount = calc[22]  # target_discount (目标折扣)
                min_price = calc[21]        # min_price

                if strategy in (DiscountCalcWidget.STRATEGY_DISCOUNT_ONLY, DiscountCalcWidget.STRATEGY_BOTH):
                    if profit < 0 and target_discount is not None:
                        if target_discount < 0:
                            negative_discount_rows.append(row_num)
                            target_discount = 0
                        discount_updates[row_num] = target_discount

                if strategy in (DiscountCalcWidget.STRATEGY_PRICE_ONLY, DiscountCalcWidget.STRATEGY_BOTH):
                    if profit < 0 and min_price is not None:
                        price_updates[row_num] = min_price

            svc = ExcelService()
            svc.write_updates(file_path, save_path, discount_updates, price_updates)
            self.status_label.setText(f"已导出: {save_path}")

            # 构建提示信息
            msg = f"结果已保存到:\n{save_path}\n\n折扣更新: {len(discount_updates)} 行\n价格更新: {len(price_updates)} 行"
            if negative_discount_rows:
                msg += f"\n\n⚠ 以下行的目标折扣为负数，已修正为0:\n行号: {negative_discount_rows[:20]}"
                if len(negative_discount_rows) > 20:
                    msg += f" ...等共{len(negative_discount_rows)}行"

            QMessageBox.information(self, "导出成功", msg)
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
        scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        container = QWidget()
        container.setMaximumWidth(560)
        container.setObjectName("settingsContainer")
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

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
