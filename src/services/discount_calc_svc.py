# -*- coding: utf-8 -*-
"""折扣推算服务 — 导入Excel + 两步匹配 + 计算"""

import logging
import math
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
                  shipping_config: ShippingConfig = None,
                  progress_callback=None,
                  should_stop=None) -> int:
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

        for idx, raw in enumerate(raw_rows):
            if should_stop and should_stop():
                break

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

            # Convert RUB fee params to CNY using exchange_rate
            if exchange_rate > 0 and exchange_rate != 1.0:
                params.dropship_fee = params.dropship_fee / exchange_rate
                params.pack_fee = params.pack_fee / exchange_rate
                params.scan_fee = params.scan_fee / exchange_rate
                params.return_pickup_fee = params.return_pickup_fee / exchange_rate
                params.return_process_fee = params.return_process_fee / exchange_rate
                params.ad_fixed = params.ad_fixed / exchange_rate

            calc = LossCalculator(params)

            l, w, h = LossCalculator.parse_dimensions(result.dimensions)
            if l == 0 and w == 0 and h == 0:
                l, w, h = LossCalculator.parse_dimensions(Config.DEFAULT_DIMENSIONS)

            # ALL CNY: discounted_price, product_cost, shipping_fee(all from calc) are CNY
            # calc_full_result uses current_price for profit calc (should be discounted_price)
            # and for discount calc (should be original_price) — so we do it manually
            calc_result = calc.calc_full_result(result.discounted_price, result.product_cost, l, w, h)

            result.shipping_fee = round(calc_result.shipping_fee, 2)
            result.breakeven = round(calc_result.breakeven, 2)
            result.profit = round(calc_result.current_profit, 2)
            result.min_price = round(calc_result.min_price, 2)
            result.target_price = round(calc_result.target_price, 2) if calc_result.target_price else None
            # Discounts calculated against original price (优惠折扣)
            result.max_discount = calc.calc_max_discount_no_loss(current_price, calc_result.breakeven)
            result.target_discount = calc.calc_target_discount(current_price, calc_result.target_price)

            results.append(result)
            if progress_callback:
                progress_callback(len(raw_rows), idx + 1)

        # Clear previous results and save new
        self.db.clear_calc_results()
        count = self.db.insert_calc_results_batch(results)
        logger.info(f"Calculated {count} results, batch={calc_batch}")
        return count

    def match(self, commission_table: str = "commission_wb_cross_border",
              exchange_rate: float = 1.0,
              progress_callback=None,
              should_stop=None) -> int:
        """Step 1: Match SKU + commission + calculate shipping.
        Stores intermediate results in calc_results (profit fields = None).
        Returns matched count.

        Args:
            commission_table: 佣金表名 (e.g. "commission_wb_local", "commission_wb_cross_border")
            exchange_rate: CNY→RUB 汇率, 用于将分销价格(RUB)转换为CNY
        """
        raw_rows = self.db.get_import_rows()
        if not raw_rows:
            return 0

        # Determine shop_type from commission_table
        shop_type = "wb_local" if "local" in (commission_table or "") else "wb_cross_border"

        matcher = ProductMatcher(self._feishu_db)
        comm_svc = CommissionService(self._commission_db)
        match_batch = datetime.now().isoformat()

        # ── 性能优化: 预加载到内存，消除逐行DB查询 ──
        matcher.preload_all()

        # 缓存佣金表列表
        _cached_commission_tables = comm_svc.db.get_commission_tables()
        _cached_table_names = [t.table_name for t in _cached_commission_tables]

        # 缓存运费配置和币种
        _cached_shipping_config = self._shipping_svc.get_config(shop_type) if self._shipping_svc else None
        _cached_shipping_currency = self._shipping_svc.get_currency(shop_type) if self._shipping_svc else "CNY"

        results = []
        for idx, raw in enumerate(raw_rows):
            if should_stop and should_stop():
                break

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
                result.distribution_price = product.distribution_price  # 原始RUB
                result.product_cost = (product.distribution_price / exchange_rate
                                       if exchange_rate > 0 else product.distribution_price)
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

            # Match category → Commission rate（使用缓存的佣金表列表）
            parts = commission_table.replace("commission_", "").split("_", 1)
            platform = parts[0] if parts else "wb"
            shop_t = parts[1] if len(parts) > 1 else "local"

            category = result.product_category or str(raw[2] or "")
            _tbl_name = f"commission_{platform}_{shop_t}"
            if _tbl_name in _cached_table_names:
                comm_rate = comm_svc.db.find_rate_in_table(_tbl_name, category, "rate_col_0")
                if comm_rate is not None:
                    matched, source = True, "product"
                else:
                    comm_rate = Config.DEFAULT_COMMISSION_RATE
                    matched, source = False, "default"
            else:
                comm_rate = comm_svc.db.find_commission_by_product(category, platform, shop_t)
                if comm_rate is not None:
                    matched, source = True, "product"
                else:
                    comm_rate = comm_svc.db.find_commission_by_category(category, platform, shop_t)
                    if comm_rate is not None:
                        matched, source = True, "category"
                    else:
                        comm_rate = Config.DEFAULT_COMMISSION_RATE
                        matched, source = False, "default"

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

            # 计算运费（使用预加载的配置，不逐行查DB）
            if _cached_shipping_config:
                _vol = l * w * h / 1000
                if shop_type == "wb_local":
                    if _vol <= 1:
                        raw_shipping = 32.0
                    else:
                        raw_shipping = 46 + (math.ceil(_vol) - 1) * 14
                else:
                    _cfg = _cached_shipping_config
                    _v = math.ceil(_vol) if _cfg["ceil_volume"] else _vol
                    raw_shipping = _cfg["base_fee"] + max(0, _v - 1) * _cfg["rate_per_unit"]
                target_is_cny = (exchange_rate != 1.0)
                if target_is_cny and _cached_shipping_currency == "RUB":
                    result.shipping_fee = round(raw_shipping / exchange_rate, 2)
                else:
                    result.shipping_fee = round(raw_shipping, 2)
            elif self._shipping_svc:
                result.shipping_fee = round(self._shipping_svc.calc_fee(l, w, h, shop_type), 2)

            # Compute discounted_price from current price + discount
            discount = raw[13] if raw[13] is not None else 0
            result.discounted_price = current_price * (1 - discount / 100) if discount else current_price

            # breakeven, profit, max_discount, min_price, target_discount, target_price remain None
            results.append(result)
            if progress_callback:
                progress_callback(len(raw_rows), idx + 1)

        self.db.clear_calc_results()
        count = self.db.insert_calc_results_batch(results)
        logger.info(f"Matched {count} rows, shop_type={shop_type}, batch={match_batch}")
        return count

    def calculate_from_match(self, params_dict: dict, exchange_rate: float = 1.0) -> int:
        """Step 2: Calculate profit/discount using matched results.
        Reads calc_results (populated by match()), computes breakeven/profit/discount.

        Args:
            params_dict: CalculationParams fields as dict
            exchange_rate: CNY→RUB 汇率, 用于将 discounted_price(RUB) 转换为 CNY
        """
        results = self.db.get_calc_results()
        if not results:
            return 0

        # Preload import rows to get original prices (before discount)
        import_rows = self.db.get_import_rows()
        import_by_id = {row[0]: row for row in import_rows}

        calc_batch = datetime.now().isoformat()
        updated = []

        for r in results:
            # r is a tuple from calc_results (29 columns):
            # (0=id, 1=import_row_id, 2=sku_matched, 3=category_matched,
            #  4=matched_product_id, 5=product_cost, 6=distribution_price,
            #  7=product_category, 8=dimensions, 9=weight,
            #  10=inventory, 11=inventory_status, 12=seller_stock, 13=wb_stock,
            #  14=commission_rate, 15=commission_source,
            #  16=discounted_price, 17=shipping_fee,
            #  18=breakeven, 19=profit, 20=max_discount, 21=min_price,
            #  22=target_discount, 23=target_price,
            #  24=cbase, 25=crisk, 26=r_total, 27=total_fixed,
            #  28=calc_batch)

            # Only calculate if sku was matched and we have product_cost
            if not r[2]:  # sku_matched == False
                continue

            if r[5] is None:
                continue

            # ALL CNY: product_cost(CNY), shipping_fee(CNY)
            product_cost = float(r[5])  # CNY
            shipping_fee = float(r[17]) if r[17] else 0.0  # CNY

            # Get prices from import_rows (source of truth)
            # raw[10]=current_price(原价), raw[12]=current_discount
            imp = import_by_id.get(r[1])
            if imp:
                try:
                    original_price = float(str(imp[10]).replace(",", "").strip())
                except (ValueError, TypeError):
                    original_price = float(r[16]) if r[16] else 0.0
                try:
                    discount = float(imp[12]) if imp[12] is not None else 0.0
                except (ValueError, TypeError):
                    discount = 0.0
                selling_price = original_price * (1 - discount / 100) if discount else original_price
            else:
                original_price = float(r[16]) if r[16] else 0.0
                selling_price = original_price  # fallback

            params = CalculationParams(**params_dict)
            params.commission_rate = float(r[14]) if r[14] else params.commission_rate  # commission_rate at index 14

            # Convert RUB fee params to CNY using exchange_rate
            if exchange_rate > 0 and exchange_rate != 1.0:
                params.dropship_fee = params.dropship_fee / exchange_rate
                params.pack_fee = params.pack_fee / exchange_rate
                params.scan_fee = params.scan_fee / exchange_rate
                params.return_pickup_fee = params.return_pickup_fee / exchange_rate
                params.return_process_fee = params.return_process_fee / exchange_rate
                params.ad_fixed = params.ad_fixed / exchange_rate

            calc = LossCalculator(params)
            cbase = calc.calc_cbase(product_cost, shipping_fee)
            crisk = calc.calc_crisk(product_cost, shipping_fee)
            r_total = calc.calc_r_total()
            total_fixed = calc.calc_total_fixed(product_cost, shipping_fee)
            breakeven = calc.calc_breakeven(product_cost, shipping_fee)
            profit = calc.calc_profit(selling_price, product_cost, shipping_fee)
            min_price = calc.calc_min_price_no_loss(breakeven)
            target_price = calc.calc_target_price(breakeven, params.target_profit_rate)

            # Discounts are calculated against original price (优惠折扣)
            # max_discount: how much % off from original to reach breakeven
            max_discount = calc.calc_max_discount_no_loss(original_price, breakeven)
            target_discount = calc.calc_target_discount(original_price, target_price)

            updated.append({
                "id": r[0],
                "product_cost": round(product_cost, 2),
                "shipping_fee": round(shipping_fee, 2),
                "commission_rate": float(r[14]) if r[14] else None,
                "discounted_price": round(selling_price, 2),
                "breakeven": round(breakeven, 2),
                "profit": round(profit, 2),
                "max_discount": max_discount,
                "min_price": round(min_price, 2),
                "target_discount": target_discount,
                "target_price": round(target_price, 2) if target_price else None,
                "cbase": round(cbase, 2),
                "crisk": round(crisk, 2),
                "r_total": round(r_total, 4),
                "total_fixed": round(total_fixed, 2),
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
                        target_discount=?, target_price=?,
                        cbase=?, crisk=?, r_total=?, total_fixed=?,
                        calc_batch=?
                    WHERE id=?
                """, (
                    u["product_cost"], u["shipping_fee"], u["commission_rate"],
                    u["discounted_price"], u["breakeven"], u["profit"],
                    u["max_discount"], u["min_price"],
                    u["target_discount"], u["target_price"],
                    u["cbase"], u["crisk"], u["r_total"], u["total_fixed"],
                    u["calc_batch"],
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
        # 25-column layout: profit at index 19
        profit = sum(1 for r in results if r[19] is not None and r[19] > 0)
        loss = sum(1 for r in results if r[19] is not None and r[19] < 0)
        unmatched = sum(1 for r in results if r[19] is None)
        sku_matched = sum(1 for r in results if r[2])   # sku_matched column
        cat_matched = sum(1 for r in results if r[3])   # category_matched column
        return {
            "total": len(results),
            "profit": profit,
            "loss": loss,
            "unmatched": unmatched,
            "sku_matched": sku_matched,
            "cat_matched": cat_matched,
        }
