# -*- coding: utf-8 -*-
"""
Tests for the core calculation engine.
Formulas verified against index.html JavaScript (lines 610-678).

Default params from index.html:
  dim=51*14*5, risk=1.00, cost=132, drop=10, pack=0, ship=13.14, scan=1,
  pickup=0, process=10, resLoss=15%, dmgRate=2%, retRate=15%,
  commRate=10%, commDisc=0%, withdrawFee=1%, adFixed=0, adPct=2.5%,
  opsPct=3%, memDisc=3%, price=230
"""

import pytest
import math
from src.services.calculator import LossCalculator, CalculationParams, CalculationResult


# ──────────────────────────── helpers ────────────────────────────

def _default_calc() -> LossCalculator:
    """Calculator with index.html default parameters."""
    return LossCalculator(CalculationParams())


def _custom_calc(**overrides) -> LossCalculator:
    """Calculator with selected overrides on defaults."""
    return LossCalculator(CalculationParams(**overrides))


# ══════════════════════════════════════════════════════════════════
#  TestShippingFee  —  (L*W*H)/1000 * 2 + 6
# ══════════════════════════════════════════════════════════════════

class TestShippingFee:
    calc = _default_calc()

    def test_standard(self):
        # 51*14*5 = 3570; 3570/1000 = 3.57; 3.57*2 = 7.14; 7.14+6 = 13.14
        assert self.calc.calc_shipping_fee(51, 14, 5) == pytest.approx(13.14, abs=0.01)

    def test_zero_dimensions(self):
        # 0*0*0 = 0; 0/1000*2+6 = 6.0
        assert self.calc.calc_shipping_fee(0, 0, 0) == pytest.approx(6.0)

    def test_large(self):
        # 100*50*30 = 150000; /1000 = 150; *2 = 300; +6 = 306
        assert self.calc.calc_shipping_fee(100, 50, 30) == pytest.approx(306.0)


# ══════════════════════════════════════════════════════════════════
#  TestCbase  —  (cost+drop+pack+ship+scan)*risk / (1-dmgRate)
# ══════════════════════════════════════════════════════════════════

class TestCbase:
    def test_standard(self):
        # cost=132, drop=10, pack=0, ship=13.14, scan=1 → sum=156.14
        # risk=1.0, dmg=2% → 156.14 / 0.98 = 159.3265...
        calc = _default_calc()
        result = calc.calc_cbase(132, 13.14)
        assert result == pytest.approx(159.3265, abs=0.01)

    def test_with_risk_factor(self):
        # risk=1.05 → sum*1.05 / 0.98
        calc = _custom_calc(risk_rate=1.05)
        result = calc.calc_cbase(132, 13.14)
        expected = 156.14 * 1.05 / 0.98
        assert result == pytest.approx(expected, abs=0.01)

    def test_with_damage_rate(self):
        # dmg=5% → sum / 0.95
        calc = _custom_calc(damage_rate=5.0)
        result = calc.calc_cbase(132, 13.14)
        expected = 156.14 / 0.95
        assert result == pytest.approx(expected, abs=0.01)

    def test_zero_damage(self):
        # dmg=0% → denominator is 1.0
        calc = _custom_calc(damage_rate=0.0)
        result = calc.calc_cbase(100, 10)
        expected = (100 + 10 + 0 + 10 + 1)  # sum * 1.0 / 1.0
        assert result == pytest.approx(expected, abs=0.01)


# ══════════════════════════════════════════════════════════════════
#  TestCrisk  —  retRate * (drop+ship+scan+pickup+process+cost*resLoss)
# ══════════════════════════════════════════════════════════════════

class TestCrisk:
    def test_standard(self):
        # lossPerReturn = 10+13.14+1+0+10+132*0.15 = 53.94
        # Crisk = 0.15 * 53.94 = 8.091
        calc = _default_calc()
        result = calc.calc_crisk(132, 13.14)
        assert result == pytest.approx(8.091, abs=0.01)

    def test_zero_return_rate(self):
        calc = _custom_calc(return_rate=0.0)
        result = calc.calc_crisk(132, 13.14)
        assert result == pytest.approx(0.0)


# ══════════════════════════════════════════════════════════════════
#  TestRTotal  —  RealComm + effWithdraw + adPct + opsPct + memDisc
# ══════════════════════════════════════════════════════════════════

class TestRTotal:
    def test_standard(self):
        # RealComm = 0.10*(1-0) = 0.10
        # effWithdraw = 0.01*(1-0.10) = 0.009
        # R_Total = 0.10 + 0.009 + 0.025 + 0.03 + 0.03 = 0.194
        calc = _default_calc()
        result = calc.calc_r_total()
        assert result == pytest.approx(0.194, abs=0.001)

    def test_with_commission_discount(self):
        # commDisc=50% → RealComm = 0.10*(1-0.50) = 0.05
        # effWithdraw = 0.01*(1-0.05) = 0.0095
        # R_Total = 0.05 + 0.0095 + 0.025 + 0.03 + 0.03 = 0.1445
        calc = _custom_calc(commission_discount=50.0)
        result = calc.calc_r_total()
        assert result == pytest.approx(0.1445, abs=0.001)


# ══════════════════════════════════════════════════════════════════
#  TestTotalFixed  —  Cbase + Crisk + adFixed - ship*withdrawRate
# ══════════════════════════════════════════════════════════════════

class TestTotalFixed:
    def test_standard(self):
        # Cbase ≈ 159.3265, Crisk ≈ 8.091, adFixed=0
        # withdrawSaving = 13.14 * 0.01 = 0.1314
        # Total_Fixed = 159.3265 + 8.091 + 0 - 0.1314 = 167.2861
        calc = _default_calc()
        result = calc.calc_total_fixed(132, 13.14)
        assert result == pytest.approx(167.2861, abs=0.01)


# ══════════════════════════════════════════════════════════════════
#  TestBreakEven  —  Total_Fixed / (1 - R_Total)
# ══════════════════════════════════════════════════════════════════

class TestBreakEven:
    def test_standard(self):
        # BreakEven = 167.2861 / (1 - 0.194) = 167.2861 / 0.806
        calc = _default_calc()
        result = calc.calc_breakeven(132, 13.14)
        expected = 167.2861 / 0.806
        assert result == pytest.approx(expected, abs=0.05)

    def test_zero_fixed(self):
        # With zero cost, drop, pack, scan, return_rate=0, dmg=0:
        # Cbase = 0+0+0+6+0 = 6.0 * 1.0 / 1.0 = 6.0
        # Crisk = 0 (return_rate=0)
        # withdrawSaving = 6*0.01 = 0.06
        # Total_Fixed = 6.0 + 0 + 0 - 0.06 = 5.94
        # R_Total = 0.194
        # BreakEven = 5.94 / 0.806 ≈ 7.37
        calc = _custom_calc(
            risk_rate=1.0, dropship_fee=0, pack_fee=0, scan_fee=0,
            return_rate=0, damage_rate=0
        )
        result = calc.calc_breakeven(0, 6.0)
        assert result == pytest.approx(7.37, abs=0.01)


# ══════════════════════════════════════════════════════════════════
#  TestProfit  —  price - price*R_Total - Total_Fixed
# ══════════════════════════════════════════════════════════════════

class TestProfit:
    def test_profit_at_given_price(self):
        # price=230, R_Total=0.194, Total_Fixed≈167.2861
        # profit = 230 - 230*0.194 - 167.2861 = 230 - 44.62 - 167.2861 ≈ 18.09
        calc = _default_calc()
        result = calc.calc_profit(230, 132, 13.14)
        assert result == pytest.approx(18.09, abs=0.5)

    def test_loss_scenario(self):
        # Price below breakeven → negative profit
        calc = _default_calc()
        result = calc.calc_profit(100, 132, 13.14)
        assert result < 0

    def test_zero_profit_at_breakeven(self):
        # At breakeven price, profit ≈ 0
        calc = _default_calc()
        breakeven = calc.calc_breakeven(132, 13.14)
        result = calc.calc_profit(breakeven, 132, 13.14)
        assert result == pytest.approx(0.0, abs=0.01)


# ══════════════════════════════════════════════════════════════════
#  TestMaxDiscount  —  floor((1 - breakeven/price)*100), clamped [0, 95]
# ══════════════════════════════════════════════════════════════════

class TestMaxDiscount:
    calc = _default_calc()

    def test_standard(self):
        # breakeven≈207.55, price=230
        # (1 - 207.55/230)*100 = (1 - 0.9024)*100 = 9.76 → floor = 9
        breakeven = 207.55
        result = self.calc.calc_max_discount_no_loss(230, breakeven)
        assert result == 9

    def test_breakeven_equals_price(self):
        result = self.calc.calc_max_discount_no_loss(200, 200)
        assert result == 0

    def test_price_below_breakeven(self):
        result = self.calc.calc_max_discount_no_loss(100, 200)
        assert result == 0

    def test_discount_exceeds_95(self):
        # Very low breakeven relative to price
        result = self.calc.calc_max_discount_no_loss(1000, 10)
        # raw = floor((1 - 10/1000)*100) = floor(99.0) = 99 → clamped to 95
        assert result == 95

    def test_zero_price(self):
        result = self.calc.calc_max_discount_no_loss(0, 100)
        assert result == 0


# ══════════════════════════════════════════════════════════════════
#  TestMinPrice  —  max(breakeven, PRICE_MIN)
# ══════════════════════════════════════════════════════════════════

class TestMinPrice:
    calc = _default_calc()

    def test_at_zero_discount(self):
        # min_price should equal breakeven when breakeven > PRICE_MIN
        breakeven = 207.55
        result = self.calc.calc_min_price_no_loss(breakeven)
        assert result == pytest.approx(breakeven, abs=0.01)

    def test_clamp(self):
        # breakeven below PRICE_MIN(5) → clamped to 5
        result = self.calc.calc_min_price_no_loss(2.0)
        assert result == pytest.approx(5.0)


# ══════════════════════════════════════════════════════════════════
#  TestCurrencyConversion
# ══════════════════════════════════════════════════════════════════

class TestCurrencyConversion:
    def test_rub_to_cny(self):
        # 100 RUB / 12.34 = 8.10 CNY
        result = LossCalculator.convert_currency(100, 12.34, to_cny=True)
        assert result == pytest.approx(8.10, abs=0.01)

    def test_cny_to_rub(self):
        # 100 CNY * 12.34 = 1234 RUB
        result = LossCalculator.convert_currency(100, 12.34, to_cny=False)
        assert result == pytest.approx(1234.0)

    def test_identity(self):
        result = LossCalculator.convert_currency(100, 1.0, to_cny=True)
        assert result == pytest.approx(100.0)


# ══════════════════════════════════════════════════════════════════
#  TestParseDimensions
# ══════════════════════════════════════════════════════════════════

class TestParseDimensions:
    def test_standard(self):
        result = LossCalculator.parse_dimensions("51*14*5")
        assert result == (51.0, 14.0, 5.0)

    def test_with_x(self):
        result = LossCalculator.parse_dimensions("30x20x10")
        assert result == (30.0, 20.0, 10.0)

    def test_invalid(self):
        result = LossCalculator.parse_dimensions("abc")
        assert result == (0.0, 0.0, 0.0)


# ══════════════════════════════════════════════════════════════════
#  TestCalcFullResult  —  integration: all fields populated correctly
# ══════════════════════════════════════════════════════════════════

class TestCalcFullResult:
    def test_default_scenario(self):
        calc = _default_calc()
        r = calc.calc_full_result(230, 132, 51, 14, 5)

        assert isinstance(r, CalculationResult)
        assert r.shipping_fee == pytest.approx(13.14, abs=0.01)
        assert r.cbase == pytest.approx(159.3265, abs=0.01)
        assert r.crisk == pytest.approx(8.091, abs=0.01)
        assert r.r_total == pytest.approx(0.194, abs=0.001)
        assert r.breakeven == pytest.approx(167.2861 / 0.806, abs=0.05)
        assert r.current_profit == pytest.approx(18.09, abs=0.5)
        assert isinstance(r.max_discount, int)
        assert r.min_price >= 5
