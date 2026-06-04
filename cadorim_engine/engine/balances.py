"""Derived balances — computed from engine_transactions and engine_settlements."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cadorim_engine.models.computed import EngineTransaction, EngineSettlement
from cadorim_engine.models.registries import Partner, Bank, LocalPartner


async def compute_local_balances(session: AsyncSession) -> list[dict]:
    """Balance_Local_Par_n = sum of MRU paid out per local partner."""
    stmt = (
        select(LocalPartner.code, LocalPartner.name,
               func.coalesce(func.sum(EngineTransaction.amount_mru), 0).label("total"),
               func.count(EngineTransaction.id).label("cnt"))
        .join(EngineTransaction, EngineTransaction.local_partner_id == LocalPartner.id)
        .where(EngineTransaction.status == "completed")
        .group_by(LocalPartner.code, LocalPartner.name)
    )
    return [{"local_partner": r.code, "name": r.name, "total_paid_out": r.total, "n_transactions": r.cnt}
            for r in (await session.execute(stmt)).all()]


async def compute_bank_balances(session: AsyncSession) -> list[dict]:
    """Balance_Bank_t = sum of settlements per bank."""
    stmt = (
        select(Bank.code, Bank.name,
               func.coalesce(func.sum(EngineSettlement.amount_original), 0).label("total"),
               func.coalesce(func.sum(EngineSettlement.gain_sett), 0).label("gain"),
               func.count(EngineSettlement.id).label("cnt"))
        .join(EngineSettlement, EngineSettlement.bank_id == Bank.id)
        .group_by(Bank.code, Bank.name)
    )
    return [{"bank": r.code, "name": r.name, "total_settled": r.total, "total_gain": r.gain, "n_settlements": r.cnt}
            for r in (await session.execute(stmt)).all()]


async def compute_receivables(session: AsyncSession) -> list[dict]:
    """Receivable_Par_l = sum of Amount_j where unsettled (international only)."""
    stmt = (
        select(Partner.code, Partner.name,
               func.coalesce(func.sum(EngineTransaction.amount_original), 0).label("receivable"),
               func.count(EngineTransaction.id).label("cnt"))
        .join(EngineTransaction, EngineTransaction.partner_id == Partner.id)
        .where(EngineTransaction.status == "completed",
               EngineTransaction.settlement_status != "settled",
               EngineTransaction.flow_type == "international_remittance")
        .group_by(Partner.code, Partner.name)
    )
    return [{"partner": r.code, "name": r.name, "receivable": r.receivable, "n_unsettled": r.cnt}
            for r in (await session.execute(stmt)).all()]


async def compute_payables(session: AsyncSession) -> list[dict]:
    """Payable_Local_Par_n = sum where payout pending."""
    stmt = (
        select(LocalPartner.code, LocalPartner.name,
               func.coalesce(func.sum(EngineTransaction.amount_mru), 0).label("payable"),
               func.count(EngineTransaction.id).label("cnt"))
        .join(EngineTransaction, EngineTransaction.local_partner_id == LocalPartner.id)
        .where(EngineTransaction.status == "pending")
        .group_by(LocalPartner.code, LocalPartner.name)
    )
    return [{"local_partner": r.code, "name": r.name, "payable": r.payable, "n_pending": r.cnt}
            for r in (await session.execute(stmt)).all()]


async def compute_all_balances(session: AsyncSession) -> dict:
    return {
        "local_partner_balances": await compute_local_balances(session),
        "bank_balances": await compute_bank_balances(session),
        "receivables_by_partner": await compute_receivables(session),
        "payables_by_local": await compute_payables(session),
    }
