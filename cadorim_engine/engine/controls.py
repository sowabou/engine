"""Automated validation controls — run before posting."""
from decimal import Decimal
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from cadorim_engine.models.computed import EngineTransaction


async def validate_transaction(tx: dict, session: AsyncSession, config=None) -> list[str]:
    """Run all controls. Returns list of warning/error strings."""
    errors = []

    # 1. Duplicate: same source_table + source_id
    dup = (await session.execute(
        select(EngineTransaction.id).where(and_(
            EngineTransaction.source_table == tx["source_table"],
            EngineTransaction.source_id == tx["source_id"],
        ))
    )).scalar_one_or_none()
    if dup is not None:
        errors.append(f"DUPLICATE: {tx['source_table']}#{tx['source_id']} exists as #{dup}")

    # 2. FX anomaly (international only) — rate >2% from market
    if config and tx.get("fx_rate") and tx["fx_rate"] != Decimal("0"):
        from datetime import datetime
        order_date = tx["date"]
        if isinstance(order_date, datetime):
            order_date = order_date.date()
        fx = config.get_fx_rate(tx["partner_id"], tx["currency_id"], order_date) if config else None
        if fx and fx.market_rate and tx["fx_rate"]:
            dev = abs(tx["fx_rate"] - fx.market_rate) / fx.market_rate if fx.market_rate else Decimal("0")
            if dev > Decimal("0.02"):
                errors.append(f"FX_ANOMALY: rate {tx['fx_rate']} deviates {dev:.2%} from market {fx.market_rate}")

    # 3. Amount integrity (international) — Amount_j × FX ≈ Amount_mru
    if tx.get("fx_rate") and tx["fx_rate"] != Decimal("0"):
        expected = (tx["amount_original"] * tx["fx_rate"]).quantize(Decimal("0.01"))
        diff = abs(expected - tx["amount_mru"])
        if diff > Decimal("1"):
            errors.append(f"AMOUNT_MISMATCH: {tx['amount_original']}×{tx['fx_rate']}={expected}, got {tx['amount_mru']} (diff={diff})")

    return errors
