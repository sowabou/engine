from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cadorim_engine.database import get_session
from cadorim_engine.models.configurations import PartnerCurrency, PartnerBank, PartnerLocalPartner, FxRate
from cadorim_engine.api.schemas.configurations import (
    PartnerCurrencyCreate, PartnerCurrencyResponse,
    PartnerBankCreate, PartnerBankResponse,
    PartnerLocalPartnerCreate as PartnerLocalCreate, PartnerLocalPartnerResponse as PartnerLocalResponse,
    FxRateCreate, FxRateResponse,
)

router = APIRouter(prefix="/engine/v1", tags=["configurations"])


@router.post("/config/partner-currencies", response_model=PartnerCurrencyResponse, status_code=201)
async def create_pc(body: PartnerCurrencyCreate, s: AsyncSession = Depends(get_session)):
    obj = PartnerCurrency(**body.model_dump())
    s.add(obj); await s.commit(); await s.refresh(obj)
    return obj

@router.get("/config/partner-currencies", response_model=list[PartnerCurrencyResponse])
async def list_pc(s: AsyncSession = Depends(get_session)):
    return (await s.execute(select(PartnerCurrency))).scalars().all()


@router.post("/config/partner-banks", response_model=PartnerBankResponse, status_code=201)
async def create_pb(body: PartnerBankCreate, s: AsyncSession = Depends(get_session)):
    obj = PartnerBank(**body.model_dump())
    s.add(obj); await s.commit(); await s.refresh(obj)
    return obj

@router.get("/config/partner-banks", response_model=list[PartnerBankResponse])
async def list_pb(s: AsyncSession = Depends(get_session)):
    return (await s.execute(select(PartnerBank))).scalars().all()


@router.post("/config/partner-locals", response_model=PartnerLocalResponse, status_code=201)
async def create_pl(body: PartnerLocalCreate, s: AsyncSession = Depends(get_session)):
    obj = PartnerLocalPartner(**body.model_dump())
    s.add(obj); await s.commit(); await s.refresh(obj)
    return obj

@router.get("/config/partner-locals", response_model=list[PartnerLocalResponse])
async def list_pl(s: AsyncSession = Depends(get_session)):
    return (await s.execute(select(PartnerLocalPartner))).scalars().all()


@router.post("/fx-rates", response_model=FxRateResponse, status_code=201)
async def create_fx(body: FxRateCreate, s: AsyncSession = Depends(get_session)):
    obj = FxRate(**body.model_dump())
    s.add(obj); await s.commit(); await s.refresh(obj)
    return obj

@router.get("/fx-rates", response_model=list[FxRateResponse])
async def list_fx(partner_id: int | None = None, s: AsyncSession = Depends(get_session)):
    stmt = select(FxRate)
    if partner_id:
        stmt = stmt.where(FxRate.partner_id == partner_id)
    return (await s.execute(stmt.order_by(FxRate.date.desc()))).scalars().all()
