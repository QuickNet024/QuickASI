import tempfile
from pathlib import Path

from src.config import Config
from src.models.database import DatabaseManager
from src.models.discount_calc import ImportRow
from src.models.product import Product
from src.models.commission import Commission
from src.services.discount_calc_svc import DiscountCalcService


def _make_db(tmp_dir: Path, name: str, tables: list[str]) -> DatabaseManager:
    return DatabaseManager(str(tmp_dir / name), init_tables=tables)


def test_match_and_calculate_use_current_discount_not_new_discount():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        calc_db = _make_db(tmp_dir, "calc.db", ["import_rows", "calc_results", "app_config"])
        feishu_db = _make_db(tmp_dir, "feishu.db", ["products"])
        commission_db = _make_db(tmp_dir, "commission.db", ["commissions", "commission_meta", "app_config"])

        feishu_db.insert_product(Product(
            sku_code="3C5-YX-JC-530-白",
            sheet_name="音响-3C5",
            distribution_price=120.0,
            dimensions="30*20*10",
            weight=0.5,
            category="音响",
            inventory=88,
            inventory_status="货源充足",
        ))
        commission_db.insert_commission(Commission(
            category="音响",
            product="音响",
            rate=12.0,
            platform="wb",
            shop_type="cross_border",
        ))
        calc_db.insert_import_rows_batch([
            ImportRow(
                row_number=2,
                category="音响",
                seller_sku="3C5-YX-JC-530-白-F4",
                current_price="100",
                current_discount=20,
                new_discount=5,
            )
        ])

        svc = DiscountCalcService(
            db=calc_db,
            feishu_db=feishu_db,
            commission_db=commission_db,
        )

        svc.match(commission_table="commission_wb_cross_border", exchange_rate=1.0)
        matched = calc_db.get_calc_results()
        assert matched[0][16] == 80.0

        svc.calculate_from_match(dict(Config.DEFAULT_PARAMS), exchange_rate=1.0)
        calculated = calc_db.get_calc_results()
        assert calculated[0][16] == 80.0
