"""Layer 2 computation — settlement gain per Par_l x Bank_t pair."""
from decimal import Decimal


def compute_settlement_gain(
    amount_original: Decimal,
    amount_converted: Decimal,
    settlement_rate: Decimal | None,
) -> Decimal:
    """gain_sett_Par_l_Bank_t = actual converted - expected converted."""
    if amount_converted and amount_original:
        if settlement_rate and settlement_rate != Decimal("0"):
            expected = (amount_original * settlement_rate).quantize(Decimal("0.01"))
            return (amount_converted - expected).quantize(Decimal("0.01"))
    return Decimal("0")
