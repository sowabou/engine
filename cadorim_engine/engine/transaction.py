"""Layer 1 computation — per-transaction profit.

All functions are parameterized. They receive config objects, not partner names.
"""
from decimal import Decimal

from cadorim_engine.models.configurations import PartnerCurrency, PartnerLocalPartner


def compute_commission(pc: PartnerCurrency | None, amount: Decimal) -> Decimal:
    """commission(Par_l, Cur_k) applied to Amount_j."""
    if pc is None:
        return Decimal("0")
    if pc.commission_type == "percentage":
        rate = pc.commission_rate or Decimal("0")
        return (amount * rate).quantize(Decimal("0.01"))
    return pc.commission_fixed or Decimal("0")


def compute_payout_cost(pl: PartnerLocalPartner | None, amount_mru: Decimal) -> Decimal:
    """cost_payout(Local_Par_n)."""
    if pl is None:
        return Decimal("0")
    cost = pl.payout_cost or Decimal("0")
    if pl.payout_cost_type == "percentage":
        return (amount_mru * cost).quantize(Decimal("0.01"))
    return cost


def compute_transaction_fx_gain(
    amount_original: Decimal,
    partner_id: int,
    currency_id: int,
    order_date,
    config,
) -> Decimal:
    """transaction_a_fx_gain = Amount_j x (cadorim_rate - partner_rate)."""
    fx_record = config.get_fx_rate(partner_id, currency_id, order_date)
    if fx_record and fx_record.cadorim_rate and fx_record.partner_rate:
        spread = fx_record.cadorim_rate - fx_record.partner_rate
        return (amount_original * spread).quantize(Decimal("0.01"))
    return Decimal("0")
