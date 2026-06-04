from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cadorim_engine.database import get_session
from cadorim_engine.models.computed import EngineSettlement
from cadorim_engine.models.registries import Partner, Bank
from cadorim_engine.api.schemas.transactions import EngineSettlementResponse

router = APIRouter(prefix="/engine/v1", tags=["settlements"])


@router.get("/settlements", response_model=list[EngineSettlementResponse])
async def list_settlements(
    partner: str | None = None, bank: str | None = None,
    limit: int = 100, offset: int = 0,
    s: AsyncSession = Depends(get_session),
):
    stmt = select(EngineSettlement)
    if partner:
        stmt = stmt.where(EngineSettlement.partner_id.in_(select(Partner.id).where(Partner.code == partner)))
    if bank:
        stmt = stmt.where(EngineSettlement.bank_id.in_(select(Bank.id).where(Bank.code == bank)))
    stmt = stmt.order_by(EngineSettlement.date.desc()).offset(offset).limit(limit)
    return (await s.execute(stmt)).scalars().all()
