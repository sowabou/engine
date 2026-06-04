from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cadorim_engine.database import get_session
from cadorim_engine.models.registries import Partner, Bank, LocalPartner, Currency
from cadorim_engine.api.schemas.registries import (
    PartnerCreate, PartnerUpdate, PartnerResponse,
    BankCreate, BankUpdate, BankResponse,
    LocalPartnerCreate, LocalPartnerUpdate, LocalPartnerResponse,
    CurrencyCreate, CurrencyUpdate, CurrencyResponse,
)

router = APIRouter(prefix="/engine/v1", tags=["registries"])


async def _create(session, cls, data):
    obj = cls(**data)
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj

async def _list(session, cls):
    return (await session.execute(select(cls))).scalars().all()

async def _get(session, cls, oid):
    obj = await session.get(cls, oid)
    if not obj:
        raise HTTPException(404, f"{cls.__name__} {oid} not found")
    return obj

async def _patch(session, cls, oid, data):
    obj = await _get(session, cls, oid)
    for k, v in data.items():
        if v is not None:
            setattr(obj, k, v)
    await session.commit()
    await session.refresh(obj)
    return obj


# Partners
@router.post("/partners", response_model=PartnerResponse, status_code=201)
async def create_partner(body: PartnerCreate, s: AsyncSession = Depends(get_session)):
    return await _create(s, Partner, body.model_dump())

@router.get("/partners", response_model=list[PartnerResponse])
async def list_partners(s: AsyncSession = Depends(get_session)):
    return await _list(s, Partner)

@router.get("/partners/{pid}", response_model=PartnerResponse)
async def get_partner(pid: int, s: AsyncSession = Depends(get_session)):
    return await _get(s, Partner, pid)

@router.patch("/partners/{pid}", response_model=PartnerResponse)
async def update_partner(pid: int, body: PartnerUpdate, s: AsyncSession = Depends(get_session)):
    return await _patch(s, Partner, pid, body.model_dump(exclude_unset=True))


# Banks
@router.post("/banks", response_model=BankResponse, status_code=201)
async def create_bank(body: BankCreate, s: AsyncSession = Depends(get_session)):
    return await _create(s, Bank, body.model_dump())

@router.get("/banks", response_model=list[BankResponse])
async def list_banks(s: AsyncSession = Depends(get_session)):
    return await _list(s, Bank)

@router.patch("/banks/{bid}", response_model=BankResponse)
async def update_bank(bid: int, body: BankUpdate, s: AsyncSession = Depends(get_session)):
    return await _patch(s, Bank, bid, body.model_dump(exclude_unset=True))


# Local Partners
@router.post("/local-partners", response_model=LocalPartnerResponse, status_code=201)
async def create_local_partner(body: LocalPartnerCreate, s: AsyncSession = Depends(get_session)):
    return await _create(s, LocalPartner, body.model_dump())

@router.get("/local-partners", response_model=list[LocalPartnerResponse])
async def list_local_partners(s: AsyncSession = Depends(get_session)):
    return await _list(s, LocalPartner)

@router.patch("/local-partners/{lid}", response_model=LocalPartnerResponse)
async def update_local_partner(lid: int, body: LocalPartnerUpdate, s: AsyncSession = Depends(get_session)):
    return await _patch(s, LocalPartner, lid, body.model_dump(exclude_unset=True))


# Currencies
@router.post("/currencies", response_model=CurrencyResponse, status_code=201)
async def create_currency(body: CurrencyCreate, s: AsyncSession = Depends(get_session)):
    return await _create(s, Currency, body.model_dump())

@router.get("/currencies", response_model=list[CurrencyResponse])
async def list_currencies(s: AsyncSession = Depends(get_session)):
    return await _list(s, Currency)

@router.patch("/currencies/{cid}", response_model=CurrencyResponse)
async def update_currency(cid: int, body: CurrencyUpdate, s: AsyncSession = Depends(get_session)):
    return await _patch(s, Currency, cid, body.model_dump(exclude_unset=True))
