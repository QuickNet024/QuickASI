# -*- coding: utf-8 -*-
"""折扣推算服务 — 导入Excel + 两步匹配 + 计算"""

import logging
from datetime import datetime
from typing import Optional

from src.config import Config
from src.models.database import DatabaseManager
from src.models.discount_calc import ImportRow, CalcResultRow
from src.services.calculator import LossCalculator, CalculationParams, ShippingConfig
from src.services.excel_service import ExcelService, ProductRow
from src.services.matcher import ProductMatcher
from src.services.commission_svc import CommissionService

logger = logging.getLogger(__name__)


class DiscountCalcService:
    def __init__(self, db: DatabaseManager = None,
                 feishu_db: DatabaseManager = None,
                 commission_db: DatabaseManager = None,
                 shipping_svc=None):
        self.db = db or DatabaseManager(Config.DB_DISCOUNT_CALC_PATH,
                                        init_tables=["import_rows", "calc_results", "app_config"])
        self._feishu_db = feishu_db
        self._commission_db = commission_db
        self._shipping_svc = shipping_svc

    def import_from_excel(self, file_path: str) -> int:
        """导入Excel文件到import_rows表。返回导入行数。"""
        svc = ExcelService()
        rows = svc.read_template(file_path)
        if not rows:
            return 0

        batch = datetime.now().isoformat()
        import_rows = []
        for r in rows:
            import_rows.append(ImportRow(
                row_number=r.row_number,
                brand=r.brand,
                category=r.category,
                wb_article=r.wb_article,
                seller_sku=r.seller_sku,
                barcode=r.barcode,
                wb_stock=str(r.wb_stock or ""),
                seller_stock=str(r.seller_stock or ""),
                turnover=r.turnover,
                current_price=r.current_price,
                new_price=r.new_price,
                current_discount=r.current_discount,
                new_discount=r.new_discount,
                import_batch=batch,
            ))

        # Clear previous import data
        self.db.clear_import_rows()
        self.db.clear_calc_results()

        count = self.db.insert_import_rows_batch(import_rows)
        logger.info(f"Imported {count} rows from {file_path}, batch={batch}")
        return count

    def calculate(self, params_dict: dict,
                  commission_table: str = "commission_wb_cross_border",
                  strategy: str = "discount_only",
                  exchange_rate: float = 1.0,
                  shipping_config: ShippingConfig = None) -> int:
        """执行两步匹配 + 计算。返回结果行数。

        Args:
            params_dict: CalculationParams 字典
            commission_table: 佣金表名 (e.g. "commission_wb_local", "commission_wb_cross_border")
            strategy: "discount_only", "price_only", "both"
            exchange_rate: CNY→RUB 汇率, 用于将分销价格(RUB)转换为CNY
            shipping_config: 运费计算配置, None则使用默认WB跨境公式
        """
        # Load imported rows
        raw_rows = self.db.get_import_rows()
        if not raw_rows:
            return 0

        # Setup matchers
        matcher = ProductMatcher(self._feishu_db)
        comm_svc = CommissionService(self._commission_db)

        calc_batch = datetime.now().isoformat()
        results = []

        for raw in raw_rows:
            result = CalcResultRow(
                import_row_id=raw[0],  # id column
                calc_batch=calc_batch,
                seller_stock=str(raw[8] or ""),  # seller_stock from import raw
                wb_stock=str(raw[7] or ""),      # wb_stock from import raw
            )

            # ── Step 1: Parse price ──
            try:
                current_price = float(str(raw[10]).replace(",", "").strip())  # current_price column
            except (ValueError, TypeError):
                result.commission_source = "价格无效"
                results.append(result)
                continue

            # ── Step 2: Match SKU → Feishu product ──
            seller_sku = str(raw[5] or "")  # seller_sku column
            product = matcher.match_product(seller_sku) if seller_sku else None

            if product:
                result.sku_matched = True
                result.matched_product_id = product.id
                result.product_cost = product.distribution_price / exchange_rate if exchange_rate > 0 else product.distribution_price
                result.product_category = product.category or ""
                result.dimensions = product.dimensions or ""
                result.inventory = product.inventory
                result.inventory_status = product.inventory_status or ""
                result.weight = product.weight if product.weight else None
            else:
                result.sku_matched = False
                result.commission_source = "产品未匹配"
                result.dimensions = Config.DEFAULT_DIMENSIONS
                results.append(result)
                continue

            # ── Step 3: Match category → Commission rate ──
            # Parse commission_table to get platform and shop_type
            # Format: "commission_wb_local" → platform="wb", shop_type="local"
            parts = commission_table.replace("commission_", "").split("_", 1)
            platform = parts[0] if parts else "wb"
            shop_type = parts[1] if len(parts) > 1 else "local"

            category = result.product_category or str(raw[2] or "")  # raw category column
            comm_rate, matched, source = comm_svc.find_commission_rate(
                category, platform=platform, shop_type=shop_type)

            result.commission_rate = comm_rate
            _SOURCE_MAP = {"product": "商品级", "category": "品类级", "default": f"未匹配(默认{Config.DEFAULT_COMMISSION_RATE:.0f}%)"}
            result.commission_source = _SOURCE_MAP.get(source, source)
            result.category_matched = matched

            # Use Config default commission rate when no match
            if not matched:
                comm_rate = Config.DEFAULT_COMMISSION_RATE
                result.commission_rate = comm_rate

            # ── Step 4: Calculate ──
            discount = raw[13] if raw[13] is not None else 0  # current_discount column
            result.discounted_price = current_price * (1 - discount / 100) if discount else current_price

            params = CalculationParams(**params_dict)
            params.commission_rate = comm_rate
            if shipping_config:
                params.shipping_config = shipping_config
            calc = LossCalculator(params)

            l, w, h = LossCalculator.parse_dimensions(result.dimensions)
            if l == 0 and w == 0 and h == 0:
                l, w, h = LossCalculator.parse_dimensions(Config.DEFAULT_DIMENSIONS)

            calc_result = calc.calc_full_result(result.discounted_price, result.product_cost, l, w, h)

            result.shipping_fee = round(calc_result.shipping_fee, 2)
            result.breakeven = round(calc_result.breakeven, 2)
            result.profit = round(calc_result.current_profit, 2)
            result.max_discount = calc_result.max_discount
            result.min_price = round(calc_result.min_price, 2)
            result.target_discount = calc_result.target_discount
            result.target_price = round(calc_result.target_price, 2) if calc_result.target_price else None

            results.append(result)

        # Clear previous results and save new
        self.db.clear_calc_results()
        count = self.db.insert_calc_results_batch(results)
        logger.info(f"Calculated {count} results, batch={calc_batch}")
        return count

    def match(self, commission_table: str = "commission_wb_cross_border") -> int:
        """Step 1: Match SKU + commission + calculate shipping.
        Stores intermediate results in calc_results (profit fields = None).
        Returns matched count.

        Args:
            commission_table: 佣金表名 (e.g. "commission_wb_local", "commission_wb_cross_border")
        """
        raw_rows = self.db.get_import_rows()
        if not raw_rows:
            return 0

        # Determine shop_type from commission_table
        shop_type = "wb_local" if "local" in (commission_table or "") else "wb_cross_border"

        matcher = ProductMatcher(self._feishu_db)
        comm_svc = CommissionService(self._commission_db)
        match_batch = datetime.now().isoformat()

        results = []
        for raw in raw_rows:
            result = CalcResultRow(
                import_row_id=raw[0],
                calc_batch=match_batch,
                seller_stock=str(raw[8] or ""),
                wb_stock=str(raw[7] or ""),
            )

            # Parse price
            try:
                current_price = float(str(raw[10]).replace(",", "").strip())
            except (ValueError, TypeError):
                result.commission_source = "价格无效"
                results.append(result)
                continue

            # Match SKU → Feishu product
            seller_sku = str(raw[5] or "")
            product = matcher.match_product(seller_sku) if seller_sku else None

            if product:
                result.sku_matched = True
                result.matched_product_id = product.id
                result.product_cost = product.distribution_price  # Divided by exchange_rate in calculate_from_match()
                result.product_category = product.category or ""
                result.dimensions = product.dimensions or ""
                result.inventory = product.inventory
                result.inventory_status = product.inventory_status or ""
                result.weight = product.weight if product.weight else None
            else:
                result.sku_matched = False
                result.commission_source = "产品未匹配"
                result.dimensions = Config.DEFAULT_DIMENSIONS
                results.append(result)
                continue

            # Match category → Commission rate
            parts = commission_table.replace("commission_", "").split("_", 1)
            platform = parts[0] if parts else "wb"
            shop_t = parts[1] if len(parts) > 1 else "local"

            category = result.product_category or str(raw[2] or "")
            comm_rate, matched, source = comm_svc.find_commission_rate(
                category, platform=platform, shop_type=shop_t)

            result.commission_rate = comm_rate
            _SOURCE_MAP = {
                "product": "商品级",
                "category": "品类级",
                "default": f"未匹配(默认{Config.DEFAULT_COMMISSION_RATE:.0f}%)",
            }
            result.commission_source = _SOURCE_MAP.get(source, source)
            result.category_matched = matched

            if not matched:
                result.commission_rate = Config.DEFAULT_COMMISSION_RATE

            # Calculate shipping using ShippingService
            l, w, h = LossCalculator.parse_dimensions(result.dimensions)
            if l == 0 and w == 0 and h == 0:
                l, w, h = LossCalculator.parse_dimensions(Config.DEFAULT_DIMENSIONS)

            if self._shipping_svc:
                result.shipping_fee = round(self._shipping_svc.calc_fee(l, w, h, shop_type), 2)
            else:
                cfg = ShippingConfig(formula=shop_type)
                params = CalculationParams(shipping_config=cfg)
                result.shipping_fee = round(LossCalculator(params).calc_shipping_fee(l, w, h), 2)

            # Compute discounted_price from current price + discount
            discount = raw[13] if raw[13] is not None else 0
            result.discounted_price = current_price * (1 - discount / 100) if discount else current_price

            # breakeven, profit, max_discount, min_price, target_discount, target_price remain None
            results.append(result)

        self.db.clear_calc_results()
        count = self.db.insert_calc_results_batch(results)
        logger.info(f"Matched {count} rows, shop_type={shop_type}, batch={match_batch}")
        return count

    def calculate_from_match(self, params_dict: dict,
                             exchange_rate: float = 1.0) -> int:
        """Step 2: Calculate profit/discount using matched results.
        Reads calc_results (populated by match()), computes breakeven/profit/discount.

        Args:
            params_dict: CalculationParams fields as dict
            exchange_rate: CNY→RUB rate for converting distribution_price to CNY
        """
        results = self.db.get_calc_results()
        if not results:
            return 0

        calc_batch = datetime.now().isoformat()
        updated = []

        for r in results:
            # r is a tuple from calc_results
            # Only calculate if sku was matched and we have product_cost
            if not r[2]:  # sku_matched == False
                continue

            product_cost_raw = r[5]  # product_cost (distribution_price in RUB)
            if product_cost_raw is None:
                continue

            product_cost = float(product_cost_raw) / exchange_rate if exchange_rate > 0 else float(product_cost_raw)
            shipping_fee = float(r[16]) if r[16] else 0.0  # shipping_fee already calculated in match()
            current_price = float(r[15]) if r[15] else 0.0  # discounted_price

            params = CalculationParams(**params_dict)
            params.commission_rate = float(r[13]) if r[13] else params.commission_rate  # from match

            calc = LossCalculator(params)
            breakeven = calc.calc_breakeven(product_cost, shipping_fee)
            profit = calc.calc_profit(current_price, product_cost, shipping_fee)
            max_discount = calc.calc_max_discount_no_loss(current_price, breakeven)
            min_price = calc.calc_min_price_no_loss(breakeven)
            target_price = calc.calc_target_price(breakeven, params.target_profit_rate)
            target_discount = calc.calc_target_discount(current_price, target_price)

            updated.append({
                "id": r[0],
                "product_cost": round(product_cost, 2),
                "shipping_fee": round(shipping_fee, 2),
                "commission_rate": float(r[13]) if r[13] else None,
                "discounted_price": round(current_price, 2),
                "breakeven": round(breakeven, 2),
                "profit": round(profit, 2),
                "max_discount": max_discount,
                "min_price": round(min_price, 2),
                "target_discount": target_discount,
                "target_price": round(target_price, 2),
                "calc_batch": calc_batch,
            })

        count = self._update_calc_results(updated)
        logger.info(f"Calculated {count} results from match, batch={calc_batch}")
        return count

    def _update_calc_results(self, updates: list) -> int:
        """Update calc_results rows with calculated values."""
        if not updates:
            return 0
        with self.db._get_conn() as conn:
            for u in updates:
                conn.execute("""
                    UPDATE calc_results SET
                        product_cost=?, shipping_fee=?, commission_rate=?,
                        discounted_price=?, breakeven=?, profit=?,
                        max_discount=?, min_price=?,
                        target_discount=?, target_price=?, calc_batch=?
                    WHERE id=?
                """, (
                    u["product_cost"], u["shipping_fee"], u["commission_rate"],
                    u["discounted_price"], u["breakeven"], u["profit"],
                    u["max_discount"], u["min_price"],
                    u["target_discount"], u["target_price"], u["calc_batch"],
                    u["id"],
                ))
        return len(updates)

    def get_import_data(self) -> list:
        """获取导入数据和计算结果的联合视图。
        返回 [(import_row_tuple, calc_result_tuple_or_None), ...]
        """
        import_rows = self.db.get_import_rows()
        calc_results = self.db.get_calc_results()

        # Build lookup: import_row_id → calc_result
        result_map = {}
        for r in calc_results:
            result_map[r[1]] = r  # r[1] = import_row_id

        combined = []
        for imp in import_rows:
            calc = result_map.get(imp[0])  # imp[0] = id
            combined.append((imp, calc))
        return combined

    def get_summary(self) -> dict:
        """获取计算摘要"""
        results = self.db.get_calc_results()
        profit = sum(1 for r in results if r[18] is not None and r[18] > 0)  # profit column
        loss = sum(1 for r in results if r[18] is not None and r[18] < 0)
        unmatched = sum(1 for r in results if r[18] is None)
        sku_matched = sum(1 for r in results if r[2])  # sku_matched column
        cat_matched = sum(1 for r in results if r[3])  # category_matched column
        return {
            "total": len(results),
            "profit": profit,
            "loss": loss,
            "unmatched": unmatched,
            "sku_matched": sku_matched,
            "cat_matched": cat_matched,
        }
