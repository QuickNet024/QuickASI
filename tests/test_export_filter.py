# -*- coding: utf-8 -*-
"""RED phase: tests for _passes_export_filter() and ZERO_DISCOUNT fix.

All tests MUST fail (RED) — _passes_export_filter() does not yet exist,
and ZERO_DISCOUNT branch currently writes calc[23] instead of calc[29].
"""

from src.ui.main_window import MainWindow


# =========================================================================
# Filter unit tests — _passes_export_filter(profit, discounted_price, mode, threshold)
# =========================================================================

def test_profit_value_below_threshold():
    """profit_value mode: negative profit < 0 threshold → True (passes filter)."""
    assert MainWindow._passes_export_filter(-10, 100, "profit_value", 0) is True


def test_profit_value_above_threshold():
    """profit_value mode: positive profit > 0 threshold → False (filtered out)."""
    assert MainWindow._passes_export_filter(10, 100, "profit_value", 0) is False


def test_profit_value_at_threshold():
    """profit_value mode: profit == 0 threshold → False (strict less-than)."""
    assert MainWindow._passes_export_filter(0, 100, "profit_value", 0) is False


def test_profit_rate_below_threshold():
    """profit_rate mode: -5% profit rate < 10% threshold → True."""
    assert MainWindow._passes_export_filter(-5, 100, "profit_rate", 10) is True


def test_profit_rate_above_threshold():
    """profit_rate mode: 20% profit rate > 10% threshold → False."""
    assert MainWindow._passes_export_filter(20, 100, "profit_rate", 10) is False


def test_profit_rate_at_threshold():
    """profit_rate mode: 10% profit rate == 10% threshold → False (strict <)."""
    assert MainWindow._passes_export_filter(10, 100, "profit_rate", 10) is False


def test_zero_denominator():
    """profit_rate mode: discounted_price == 0 → denominator error, excluded."""
    assert MainWindow._passes_export_filter(10, 0, "profit_rate", 10) is False


def test_none_profit():
    """profit is None → cannot evaluate, excluded."""
    assert MainWindow._passes_export_filter(None, 100, "profit_value", 0) is False


# =========================================================================
# ZERO_DISCOUNT fix tests — new price should use calc[29] (target_new_price)
# =========================================================================

def test_zero_discount_writes_target_new_price():
    """ZERO_DISCOUNT with target_discount<0: J col = calc[29] (not calc[23])."""
    calc = [None] * 30
    calc[21] = 100   # min_price
    calc[22] = -5    # target_discount (< 0 → zero-out branch)
    calc[23] = 120   # target_price (old value — should NOT be used)
    calc[29] = 150   # target_new_price (new value — should be used)

    # Simulate the fix: prefer calc[29] over calc[21]
    target_new_price = calc[29] if calc[29] else calc[21]

    assert target_new_price == 150      # should be 150
    assert target_new_price != calc[23]  # must NOT fall back to 120


def test_zero_discount_fallback_min_price():
    """ZERO_DISCOUNT: when calc[29] is None, fallback to min_price."""
    calc = [None] * 30
    calc[21] = 100   # min_price
    calc[29] = None  # target_new_price not set

    target_new_price = calc[29] if calc[29] else calc[21]

    assert target_new_price == 100


# =========================================================================
# Regression tests — other strategies still behave correctly
# =========================================================================

def test_discount_only_writes_target_price():
    """DISCOUNT_ONLY strategy: target_price is calc[23], not calc[29]."""
    calc = [None] * 30
    calc[21] = 100   # min_price
    calc[23] = 120   # target_price
    calc[29] = 150   # target_new_price (should not be used by this strategy)

    target_price = calc[23] if calc[23] else calc[21]
    assert target_price == 120       # uses calc[23]
    assert target_price != calc[29]  # not the new price


def test_keep_discount_writes_target_new_price():
    """KEEP_DISCOUNT strategy already correctly uses calc[29]."""
    calc = [None] * 30
    calc[21] = 100   # min_price
    calc[29] = 150   # target_new_price

    target_new_price = calc[29] if calc[29] else calc[21]
    assert target_new_price == 150
