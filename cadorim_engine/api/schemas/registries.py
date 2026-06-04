from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


# ── Partner ──────────────────────────────────────────────────────────────


class PartnerCreate(BaseModel):
    code: str
    name: str
    flow_type: str
    api_partner_name: str | None = None
    status: str = "active"


class PartnerUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    flow_type: str | None = None
    api_partner_name: str | None = None
    status: str | None = None


class PartnerResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    code: str
    name: str
    flow_type: str
    api_partner_name: str | None
    status: str
    created_at: datetime | None


# ── Bank ─────────────────────────────────────────────────────────────────


class BankCreate(BaseModel):
    code: str
    name: str
    currency: str
    api_bank_account_id: int | None = None
    status: str = "active"


class BankUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    currency: str | None = None
    api_bank_account_id: int | None = None
    status: str | None = None


class BankResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    code: str
    name: str
    currency: str
    api_bank_account_id: int | None
    status: str
    created_at: datetime | None


# ── LocalPartner ─────────────────────────────────────────────────────────


class LocalPartnerCreate(BaseModel):
    code: str
    name: str
    type: str
    api_account_id: int | None = None
    status: str = "active"


class LocalPartnerUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    type: str | None = None
    api_account_id: int | None = None
    status: str | None = None


class LocalPartnerResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    code: str
    name: str
    type: str
    api_account_id: int | None
    status: str
    created_at: datetime | None


# ── Currency ─────────────────────────────────────────────────────────────


class CurrencyCreate(BaseModel):
    code: str
    name: str
    decimals: int = 2


class CurrencyUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    decimals: int | None = None


class CurrencyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    code: str
    name: str
    decimals: int
    created_at: datetime | None
