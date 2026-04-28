# -*- coding: utf-8 -*-
"""
Tests for the core calculation engine.
Formulas verified against new WB跨境 shipping formula.

Default params:
  dim=51*14*5, risk=1.00, cost=132, drop=10, pack=0, ship=14, scan=1,
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
#  TestShippingFee  —  8 + (ceil(volume_L) - 1) × 2
# ══════════════════════════════════════════════════════════════════

class TestShippingFee:
    calc = _default_calc()

    def test_standard(self):
        # 51*14*5 = 3570; 3570/1000 = 3.57; ceil(3.57)=4; 8+(4-1)*2 = 14
        assert self.calc.calc_shipping_fee(51, 14, 5) == pytest.approx(14.0)

    def test_zero_dimensions(self):
        # 0*0*0 = 0; /1000 = 0; ceil(0)=0; 8+max(0,-1)*2 = 8
        assert self.calc.calc_shipping_fee(0, 0, 0) == pytest.approx(8.0)

    def test_large(self):
        # 100*50*30 = 150000; /1000 = 150; ceil(150)=150; 8+(150-1)*2 = 306
        assert self.calc.calc_shipping_fee(100, 50, 30) == pytest.approx(306.0)


# ══════════════════════════════════════════════════════════════════
#  TestCbase  —  (cost+drop+pack+ship+scan)*risk / (1-dmgRate)
# ══════════════════════════════════════════════════════════════════

class TestCbase:
    def test_standard(self):
        # cost=132, drop=10, pack=0, ship=13.14, scan=1 → sum=156.14
        # risk=1.0, dmg=2% → 156.14 / 0.98 = 159.3265...
        calc = _default_calc()
    def test_standard(self):
        # cost=132, drop=10, pack=0, ship=14, scan=1 → sum=157
        # risk=1.0, dmg=2% → 157 / 0.98 = 160.2041
        calc = _default_calc()
        result = calc.calc_cbase(132, 14)
        assert result == pytest.approx(160.2041, abs=0.01)

    def test_with_risk_factor(self):
        # risk=1.05 → sum*1.05 / 0.98
        calc = _custom_calc(risk_rate=1.05)
        result = calc.calc_cbase(132, 14)
        expected = 157.0 * 1.05 / 0.98
        assert result == pytest.approx(expected, abs=0.01)

    def test_with_damage_rate(self):
        # dmg=5% → sum / 0.95
        calc = _custom_calc(damage_rate=5.0)
        result = calc.calc_cbase(132, 14)
        expected = 157.0 / 0.95
        assert result == pytest.approx(expected, abs=0.01)

    def test_zero_damage(self):
        # dmg=0% → denominator is 1.0
        calc = _custom_calc(damage_rate=0.0)
        result = calc.calc_cbase(100, 14)
        expected = (100 + 10 + 0 + 14 + 1)  # sum * 1.0 / 1.0
        assert result == pytest.approx(expected, abs=0.01)


# ══════════════════════════════════════════════════════════════════
#  TestCrisk  —  retRate * (drop+ship+scan+pickup+process+cost*resLoss)
# ══════════════════════════════════════════════════════════════════

class TestCrisk:
    def test_standard(self):
        # lossPerReturn = 10+14+1+0+10+132*0.15 = 54.8
        # Crisk = 0.15 * 54.8 = 8.22
        calc = _default_calc()
        result = calc.calc_crisk(132, 14)
        assert result == pytest.approx(8.22, abs=0.01)

    def test_zero_return_rate(self):
        calc = _custom_calc(return_rate=0.0)
        result = calc.calc_crisk(132, 14)
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
        # Cbase ≈ 160.20, Crisk ≈ 8.22, adFixed=0
        # withdrawSaving = 14 * 0.01 = 0.14
        # Total_Fixed = 160.20 + 8.22 + 0 - 0.14 = 168.28
        calc = _default_calc()
        result = calc.calc_total_fixed(132, 14)
        assert result == pytest.approx(168.28, abs=0.1)


# ══════════════════════════════════════════════════════════════════
#  TestBreakEven  —  Total_Fixed / (1 - R_Total)
# ══════════════════════════════════════════════════════════════════

class TestBreakEven:
    def test_standard(self):
        # BreakEven = 168.28 / (1 - 0.194) = 168.28 / 0.806
        calc = _default_calc()
        result = calc.calc_breakeven(132, 14)
        expected = 168.28 / 0.806
        assert result == pytest.approx(expected, abs=0.1)

    def test_zero_fixed(self):
        # With zero cost, drop, pack, scan, return_rate=0, dmg=0:
        # shipping=8 (new formula), Cbase = 0+0+0+8+0 = 8.0 * 1.0 / 1.0 = 8.0
        # Crisk = 0 (return_rate=0)
        # withdrawSaving = 8*0.01 = 0.08
        # Total_Fixed = 8.0 + 0 + 0 - 0.08 = 7.92
        # R_Total = 0.194
        # BreakEven = 7.92 / 0.806 ≈ 9.83
        calc = _custom_calc(
            risk_rate=1.0, dropship_fee=0, pack_fee=0, scan_fee=0,
            return_rate=0, damage_rate=0
        )
        result = calc.calc_breakeven(0, 8.0)
        assert result == pytest.approx(9.83, abs=0.1)


# ══════════════════════════════════════════════════════════════════
#  TestProfit  —  price - price*R_Total - Total_Fixed
# ══════════════════════════════════════════════════════════════════

class TestProfit:
    def test_profit_at_given_price(self):
        # price=230, R_Total=0.194, Total_Fixed≈168.28
        # profit = 230 - 230*0.194 - 168.28 = 230 - 44.62 - 168.28 ≈ 17.10
        calc = _default_calc()
        result = calc.calc_profit(230, 132, 14)
        assert result == pytest.approx(17.10, abs=0.5)

    def test_loss_scenario(self):
        # Price below breakeven → negative profit
        calc = _default_calc()
        result = calc.calc_profit(100, 132, 14)
        assert result < 0

    def test_zero_profit_at_breakeven(self):
        # At breakeven price, profit ≈ 0
        calc = _default_calc()
        breakeven = calc.calc_breakeven(132, 14)
        result = calc.calc_profit(breakeven, 132, 14)
        assert result == pytest.approx(0.0, abs=0.01)


# ══════════════════════════════════════════════════════════════════
#  TestMaxDiscount  —  floor((1 - breakeven/price)*100), clamped [0, 95]
# ══════════════════════════════════════════════════════════════════

class TestMaxDiscount:
    calc = _default_calc()

    def test_standard(self):
        # breakeven≈208.66, price=230
        # (1 - 208.66/230)*100 = (1 - 0.9072)*100 = 9.28 → floor = 9
        breakeven = 208.66
        result = self.calc.calc_max_discount_no_loss(230, breakeven)
        assert result == 9

    def test_breakeven_equals_price(self):
        result = self.calc.calc_max_discount_no_loss(200, 200)
        assert result == 0

    def test_price_below_breakeven(self):
        result = self.calc.calc_max_discount_no_loss(100, 200)
        # price < breakeven → need to raise price, discount is negative
        assert result == -100

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
        breakeven = 208.66
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
        assert r.shipping_fee == pytest.approx(14.0)
        assert r.cbase == pytest.approx(160.20, abs=0.5)
        assert r.crisk == pytest.approx(8.22, abs=0.01)
        assert r.r_total == pytest.approx(0.194, abs=0.001)
        assert r.breakeven == pytest.approx(168.28 / 0.806, abs=0.1)
        assert r.current_profit == pytest.approx(17.10, abs=0.5)
        assert isinstance(r.max_discount, int)
        assert r.min_price >= 5

    def test_target_price_uses_target_margin_formula(self):
        calc = _default_calc()
        r = calc.calc_full_result(230, 132, 51, 14, 5)
        expected = r.total_fixed / (1 - r.r_total - 0.10)
        assert r.target_price == pytest.approx(expected, abs=0.01)


# ══════════════════════════════════════════════════════════════════
#  TestFixedProfit  —  (total_fixed + fixed_profit) / (1 - r_total)
# ══════════════════════════════════════════════════════════════════

class TestFixedProfit:
    """Tests for calc_target_price_fixed_profit."""

    def test_fixed_profit_basic(self):
        """total_fixed=80, r_total=0.25, fixed_profit=20 → target_price=133.33"""
        calc = LossCalculator(CalculationParams())
        result = calc.calc_target_price_fixed_profit(80.0, 0.25, 20.0)
        assert abs(result - 133.33) < 0.01  # (80+20)/(1-0.25) = 133.33

    def test_fixed_profit_zero(self):
        """fixed_profit=0 → target_price equals breakeven"""
        calc = LossCalculator(CalculationParams())
        total_fixed = 80.0
        r_total = 0.25
        fixed_result = calc.calc_target_price_fixed_profit(total_fixed, r_total, 0.0)
        breakeven_expected = total_fixed / (1 - r_total)  # 106.67
        assert abs(fixed_result - breakeven_expected) < 0.01

    def test_fixed_profit_inf(self):
        """r_total=1.0 → denominator=0 → inf"""
        calc = LossCalculator(CalculationParams())
        result = calc.calc_target_price_fixed_profit(80.0, 1.0, 20.0)
        assert result == float('inf')

    def test_profit_rate_unchanged(self):
        """Verify existing profit_rate mode is NOT affected (regression test)"""
        calc = LossCalculator(CalculationParams(target_profit_rate=10.0))
        result = calc.calc_target_price(80.0, 0.25, 10.0)
        # total_fixed=80, r_total=0.25, rate=10% → 80/(1-0.25-0.10) = 80/0.65 = 123.08
        assert abs(result - 123.08) < 0.01


# ══════════════════════════════════════════════════════════════════
#  TestTargetNewPrice  —  target_price / (1 - current_discount/100)
# ══════════════════════════════════════════════════════════════════

class TestTargetNewPrice:
    """Tests for calc_target_new_price static method."""

    def test_basic(self):
        """target_price=900, discount=20% → target_new_price=1125"""
        result = LossCalculator.calc_target_new_price(900.0, 20.0)
        assert abs(result - 1125.0) < 0.01  # 900 / 0.8 = 1125

    def test_zero_discount(self):
        """target_price=100, discount=0 → target_new_price=100"""
        result = LossCalculator.calc_target_new_price(100.0, 0.0)
        assert abs(result - 100.0) < 0.01

    def test_full_discount(self):
        """target_price=100, discount=100 → None (division by zero)"""
        result = LossCalculator.calc_target_new_price(100.0, 100.0)
        assert result is None

    def test_null_discount(self):
        """target_price=100, discount=None → 100 (treat as 0)"""
        result = LossCalculator.calc_target_new_price(100.0, None)
        assert abs(result - 100.0) < 0.01

    def test_negative_discount(self):
        """target_price=100, discount=-10 → target_new_price=90.91"""
        result = LossCalculator.calc_target_new_price(100.0, -10.0)
        assert abs(result - (100.0 / 1.10)) < 0.01  # 90.91
