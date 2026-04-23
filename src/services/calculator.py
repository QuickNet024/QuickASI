# -*- coding: utf-8 -*-
"""
WB亏损计算系统 - 核心计算引擎

Formulas from index.html JavaScript (lines 610-678):
  Shipping: (L*W*H)/1000 * 2 + 6
  Cbase:    (cost+drop+pack+ship+scan)*risk / (1-dmgRate)
  Crisk:    retRate * (drop+ship+scan+pickup+process+cost*resLoss)
  R_Total:  RealComm + effWithdraw + adPct + opsPct + memDisc
  Total_Fixed: Cbase + Crisk + adFixed - ship*withdrawRate
  BreakEven: Total_Fixed / (1 - R_Total)
  Profit:   price - price*R_Total - Total_Fixed
"""

from dataclasses import dataclass
from typing import Tuple
import math
import re

from src.config import Config


@dataclass
class CalculationParams:
    risk_rate: float = 1.00
    dropship_fee: float = 10.0
    pack_fee: float = 0.0
    scan_fee: float = 1.0
    return_process_fee: float = 10.0
    residual_loss_rate: float = 15.0
    damage_rate: float = 2.0
    return_rate: float = 15.0
    commission_rate: float = 10.0
    commission_discount: float = 0.0
    withdraw_fee: float = 1.0
    ad_fixed: float = 0.0
    ad_percent: float = 2.5
    ops_rate: float = 3.0
    member_disc: float = 3.0
    target_profit_rate: float = 10.0
    default_commission: float = 30.0


@dataclass
class CalculationResult:
    shipping_fee: float
    cbase: float
    crisk: float
    r_total: float
    total_fixed: float
    breakeven: float
    current_profit: float
    max_discount: int
    min_price: float


class LossCalculator:
    def __init__(self, params: CalculationParams = None):
        self.params = params or CalculationParams()

    # ── Platform shipping fee ──
    # (L*W*H)/1000 * 2 + 6
    def calc_shipping_fee(self, l: float, w: float, h: float) -> float:
        return (l * w * h) / 1000 * 2 + 6

    # ── Base cost with risk and damage ──
    # (cost+drop+pack+ship+scan)*risk / (1-dmgRate)
    def calc_cbase(self, product_cost: float, shipping_fee: float) -> float:
        p = self.params
        sum_logistics = product_cost + p.dropship_fee + p.pack_fee + shipping_fee + p.scan_fee
        return (sum_logistics * p.risk_rate) / (1 - p.damage_rate / 100)

    # ── Return risk cost ──
    # retRate * (drop+ship+scan+pickup+process+cost*resLoss)
    def calc_crisk(self, product_cost: float, shipping_fee: float) -> float:
        p = self.params
        loss_per_return = (
            p.dropship_fee + shipping_fee + p.scan_fee
            + p.return_process_fee
            + product_cost * p.residual_loss_rate / 100
        )
        return p.return_rate / 100 * loss_per_return

    # ── Total variable rate ──
    # RealComm + effWithdraw + adPct + opsPct + memDisc
    def calc_r_total(self) -> float:
        p = self.params
        real_comm = p.commission_rate / 100 * (1 - p.commission_discount / 100)
        eff_withdraw = p.withdraw_fee / 100 * (1 - real_comm)
        return real_comm + eff_withdraw + p.ad_percent / 100 + p.ops_rate / 100 + p.member_disc / 100

    # ── Total fixed cost ──
    # Cbase + Crisk + adFixed - ship*withdrawRate
    def calc_total_fixed(self, product_cost: float, shipping_fee: float) -> float:
        p = self.params
        withdraw_saving = shipping_fee * p.withdraw_fee / 100
        return self.calc_cbase(product_cost, shipping_fee) + self.calc_crisk(product_cost, shipping_fee) + p.ad_fixed - withdraw_saving

    # ── Break-even price ──
    # Total_Fixed / (1 - R_Total)
    def calc_breakeven(self, product_cost: float, shipping_fee: float) -> float:
        tf = self.calc_total_fixed(product_cost, shipping_fee)
        rt = self.calc_r_total()
        d = 1 - rt
        return tf / d if d > 0 else float('inf')

    # ── Profit at a given price ──
    # price - price*R_Total - Total_Fixed
    def calc_profit(self, price: float, product_cost: float, shipping_fee: float) -> float:
        return price - price * self.calc_r_total() - self.calc_total_fixed(product_cost, shipping_fee)

    # ── Max discount without loss ──
    # floor((1 - breakeven/price)*100), clamped [0, 95]
    def calc_max_discount_no_loss(self, current_price: float, breakeven: float) -> int:
        if current_price <= 0:
            return 0
        raw = math.floor((1 - breakeven / current_price) * 100)
        return max(0, min(95, raw))

    # ── Minimum price without loss ──
    # max(breakeven, PRICE_MIN)
    def calc_min_price_no_loss(self, breakeven: float) -> float:
        return max(breakeven, Config.PRICE_MIN)

    # ── Full calculation result ──
    def calc_full_result(self, current_price: float, product_cost: float,
                         l: float, w: float, h: float) -> CalculationResult:
        sf = self.calc_shipping_fee(l, w, h)
        be = self.calc_breakeven(product_cost, sf)
        return CalculationResult(
            shipping_fee=sf,
            cbase=self.calc_cbase(product_cost, sf),
            crisk=self.calc_crisk(product_cost, sf),
            r_total=self.calc_r_total(),
            total_fixed=self.calc_total_fixed(product_cost, sf),
            breakeven=be,
            current_profit=self.calc_profit(current_price, product_cost, sf),
            max_discount=self.calc_max_discount_no_loss(current_price, be),
            min_price=self.calc_min_price_no_loss(be),
        )

    # ── Currency conversion ──
    @staticmethod
    def convert_currency(amount: float, rate: float, to_cny: bool = True) -> float:
        return amount / rate if to_cny else amount * rate

    # ── Dimension string parsing ──
    @staticmethod
    def parse_dimensions(dim_str: str) -> Tuple[float, float, float]:
        matches = re.findall(r'(\d+(?:\.\d+)?)', dim_str)
        if len(matches) >= 3:
            return float(matches[0]), float(matches[1]), float(matches[2])
        return 0.0, 0.0, 0.0
