from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cadorim_engine.database import get_session
from cadorim_engine.models.computed import EngineTransaction
from cadorim_engine.models.registries import Partner, LocalPartner
from cadorim_engine.api.schemas.transactions import EngineTransactionResponse
from cadorim_engine.engine.balances import compute_all_balances

router = APIRouter(prefix="/engine/v1", tags=["transactions"])


@router.get("/transactions", response_model=list[EngineTransactionResponse])
async def list_transactions(
    partner: str | None = None, flow_type: str | None = None,
    local_partner: str | None = None, status: str | None = None,
    from_date: date | None = None, to_date: date | None = None,
    limit: int = 100, offset: int = 0,
    s: AsyncSession = Depends(get_session),
):
    stmt = select(EngineTransaction)
    if partner:
        stmt = stmt.where(EngineTransaction.partner_id.in_(select(Partner.id).where(Partner.code == partner)))
    if flow_type:
        stmt = stmt.where(EngineTransaction.flow_type == flow_type)
    if local_partner:
        stmt = stmt.where(EngineTransaction.local_partner_id.in_(select(LocalPartner.id).where(LocalPartner.code == local_partner)))
    if status:
        stmt = stmt.where(EngineTransaction.status == status)
    if from_date:
        stmt = stmt.where(EngineTransaction.date >= from_date)
    if to_date:
        stmt = stmt.where(EngineTransaction.date <= to_date)
    stmt = stmt.order_by(EngineTransaction.date.desc()).offset(offset).limit(limit)
    return (await s.execute(stmt)).scalars().all()


@router.get("/balances")
async def get_balances(s: AsyncSession = Depends(get_session)):
    return await compute_all_balances(s)
