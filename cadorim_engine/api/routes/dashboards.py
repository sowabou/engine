from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from cadorim_engine.database import get_session
from cadorim_engine.models.computed import EngineTransaction, EngineSettlement
from cadorim_engine.models.registries import Partner, Bank, LocalPartner
from cadorim_engine.engine.balances import compute_local_balances, compute_bank_balances, compute_receivables, compute_payables

router = APIRouter(prefix="/engine/v1/dashboard", tags=["dashboards"])


@router.get("/ceo")
async def ceo_dashboard(from_date: date | None = None, to_date: date | None = None, s: AsyncSession = Depends(get_session)):
    # By flow_type
    flow_stmt = (
        select(EngineTransaction.flow_type,
               func.count(EngineTransaction.id).label("cnt"),
               func.coalesce(func.sum(EngineTransaction.amount_mru), 0).label("volume"),
               func.coalesce(func.sum(EngineTransaction.profit_transaction_a), 0).label("profit"),
               func.coalesce(func.sum(EngineTransaction.commission_a), 0).label("commission"))
        .where(EngineTransaction.status == "completed")
        .group_by(EngineTransaction.flow_type)
    )
    if from_date: flow_stmt = flow_stmt.where(EngineTransaction.date >= from_date)
    if to_date: flow_stmt = flow_stmt.where(EngineTransaction.date <= to_date)
    by_flow = [{"flow_type": r.flow_type, "count": r.cnt, "volume_mru": r.volume, "profit": r.profit, "commission": r.commission}
               for r in (await s.execute(flow_stmt)).all()]

    # By partner
    partner_stmt = (
        select(Partner.code, Partner.name, Partner.flow_type,
               func.count(EngineTransaction.id).label("cnt"),
               func.coalesce(func.sum(EngineTransaction.amount_mru), 0).label("volume"),
               func.coalesce(func.sum(EngineTransaction.profit_transaction_a), 0).label("profit"))
        .join(Partner, EngineTransaction.partner_id == Partner.id)
        .where(EngineTransaction.status == "completed")
        .group_by(Partner.code, Partner.name, Partner.flow_type)
    )
    by_partner = [{"partner": r.code, "name": r.name, "flow_type": r.flow_type, "count": r.cnt, "volume_mru": r.volume, "profit": r.profit}
                  for r in (await s.execute(partner_stmt)).all()]

    receivables = await compute_receivables(s)
    return {"by_flow": by_flow, "by_partner": by_partner, "receivables": receivables}


@router.get("/operations")
async def operations_dashboard(target_date: date | None = None, s: AsyncSession = Depends(get_session)):
    if not target_date:
        target_date = date.today()
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    n_today = (await s.execute(
        select(func.count(EngineTransaction.id)).where(EngineTransaction.date >= day_start, EngineTransaction.date < day_end)
    )).scalar() or 0

    # Payout status
    status_rows = (await s.execute(
        select(EngineTransaction.status, func.count(EngineTransaction.id))
        .where(EngineTransaction.date >= day_start, EngineTransaction.date < day_end)
        .group_by(EngineTransaction.status)
    )).all()
    payout_status = {r[0]: r[1] for r in status_rows}

    local_balances = await compute_local_balances(s)
    return {"n_transactions_today": n_today, "payout_status": payout_status, "local_balances": local_balances}


@router.get("/treasury")
async def treasury_dashboard(s: AsyncSession = Depends(get_session)):
    bank_balances = await compute_bank_balances(s)
    local_balances = await compute_local_balances(s)
    receivables = await compute_receivables(s)
    payables = await compute_payables(s)

    sett_stmt = (
        select(Partner.code.label("partner"), Bank.code.label("bank"),
               func.coalesce(func.sum(EngineSettlement.gain_sett), 0).label("gain"))
        .join(Partner, EngineSettlement.partner_id == Partner.id)
        .join(Bank, EngineSettlement.bank_id == Bank.id)
        .group_by(Partner.code, Bank.code)
    )
    sett_gains = [{"partner": r.partner, "bank": r.bank, "gain": r.gain}
                  for r in (await s.execute(sett_stmt)).all()]

    total_recv = sum(r["receivable"] for r in receivables) if receivables else 0
    total_pay = sum(p["payable"] for p in payables) if payables else 0

    return {
        "bank_balances": bank_balances, "local_balances": local_balances,
        "receivables": receivables, "payables": payables,
        "settlement_gains": sett_gains, "liquidity_gap": total_recv - total_pay,
    }
