"""Unified computation — Layer 1 and Layer 2 using EngineConfig.

These are the exact formulas from the spec. They delegate to the
existing parameterized functions in transaction.py and settlement.py.
"""
from decimal import Decimal
from cadorim_engine.engine.config_loader import EngineConfig


def compute_layer1(tx: dict, config: EngineConfig) -> dict:
    """Compute all Layer 1 fields for a transaction.

    tx must have: Par_l, Cur_k, Amount_j, Amount_mru_h, Local_Par_n, date
    Returns: commission_a, cost_payout_a, fx_gain_a, gain_transaction_a, profit_transaction_a
    """
    partner_code = tx["Par_l"]
    channel_code = tx["Local_Par_n"]
    amount_j = Decimal(str(tx["Amount_j"]))
    amount_mru = Decimal(str(tx["Amount_mru_h"]))

    # Commission: what Cadorim earns — commission(Par_l, Cur_k)
    pc = config.get_commission_config(partner_code)
    if pc and pc.commission_type == "percentage":
        commission_a = (amount_j * pc.commission_rate).quantize(Decimal("0.01"))
    elif pc and pc.commission_type == "fixed":
        commission_a = pc.commission_fixed
    else:
        commission_a = Decimal("0")

    # Payout cost: what Cadorim pays the channel — cost_payout(Local_Par_n)
    ch = config.get_channel_config(partner_code, channel_code)
    if ch:
        if ch.cost_type == "percentage":
            cost_payout_a = (amount_mru * ch.cost_payout).quantize(Decimal("0.01"))
        else:
            # "fixed" or "per_transaction" — same: flat amount
            cost_payout_a = ch.cost_payout
    else:
        cost_payout_a = Decimal("0")

    # FX gain: spread between cadorim rate and partner rate
    # = 0 when Cur_k = MRU (local flows)
    fx = config.get_fx_config(partner_code)
    if fx and fx.fx_cadorim_rate > 0 and fx.fx_partner_rate > 0:
        fx_gain_a = ((fx.fx_cadorim_rate - fx.fx_partner_rate) * amount_j).quantize(Decimal("0.01"))
    else:
        fx_gain_a = Decimal("0")

    # Gain and Profit
    gain_transaction_a = commission_a - cost_payout_a
    profit_transaction_a = gain_transaction_a + fx_gain_a

    return {
        "commission_a": commission_a,
        "cost_payout_a": cost_payout_a,
        "fx_gain_a": fx_gain_a,
        "gain_transaction_a": gain_transaction_a,
        "profit_transaction_a": profit_transaction_a,
    }


def compute_layer2(settlement: dict, config: EngineConfig) -> dict:
    """Compute Layer 2 settlement gain. INDEPENDENT from Layer 1.

    settlement must have: Par_l, Bank_t, Amount_s, fx_settlement_rate, fx_reference_rate
    Returns: gain_sett_s
    """
    partner_code = settlement["Par_l"]
    bank_code = settlement["Bank_t"]
    amount_s = Decimal(str(settlement["Amount_s"]))

    # Use rates from settlement event (overrides config if provided)
    fx_sett = Decimal(str(settlement.get("fx_settlement_rate", 0)))
    fx_ref = Decimal(str(settlement.get("fx_reference_rate", 0)))

    # Fallback to config if not in settlement event
    if fx_sett == 0 or fx_ref == 0:
        sc = config.get_settlement_config(partner_code, bank_code)
        if sc:
            if fx_sett == 0:
                fx_sett = sc.fx_settlement_rate
            if fx_ref == 0:
                fx_ref = sc.fx_reference_rate

    gain_sett_s = ((fx_sett - fx_ref) * amount_s).quantize(Decimal("0.01"))

    return {"gain_sett_s": gain_sett_s}
