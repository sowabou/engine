from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


# ── PartnerCurrency ──────────────────────────────────────────────────────


class PartnerCurrencyCreate(BaseModel):
    partner_id: int
    currency_id: int
    commission_rate: Decimal | None = None
    commission_type: str = "percentage"
    commission_fixed: Decimal | None = None
    status: str = "active"


class PartnerCurrencyUpdate(BaseModel):
    commission_rate: Decimal | None = None
    commission_type: str | None = None
    commission_fixed: Decimal | None = None
    status: str | None = None


class PartnerCurrencyResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    partner_id: int
    currency_id: int
    commission_rate: Decimal | None
    commission_type: str
    commission_fixed: Decimal | None
    status: str


# ── PartnerBank ──────────────────────────────────────────────────────────


class PartnerBankCreate(BaseModel):
    partner_id: int
    bank_id: int
    status: str = "active"


class PartnerBankUpdate(BaseModel):
    status: str | None = None


class PartnerBankResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    partner_id: int
    bank_id: int
    status: str


# ── PartnerLocalPartner ─────────────────────────────────────────────────


class PartnerLocalPartnerCreate(BaseModel):
    partner_id: int
    local_partner_id: int
    payout_cost: Decimal = Decimal("0")
    payout_cost_type: str = "fixed"
    status: str = "active"


class PartnerLocalPartnerUpdate(BaseModel):
    payout_cost: Decimal | None = None
    payout_cost_type: str | None = None
    status: str | None = None


class PartnerLocalPartnerResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    partner_id: int
    local_partner_id: int
    payout_cost: Decimal
    payout_cost_type: str
    status: str


# ── FxRate ───────────────────────────────────────────────────────────────


class FxRateCreate(BaseModel):
    partner_id: int
    currency_id: int
    date: date
    partner_rate: Decimal
    market_rate: Decimal | None = None
    cadorim_rate: Decimal | None = None


class FxRateUpdate(BaseModel):
    partner_rate: Decimal | None = None
    market_rate: Decimal | None = None
    cadorim_rate: Decimal | None = None


class FxRateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    partner_id: int
    currency_id: int
    date: date
    partner_rate: Decimal
    market_rate: Decimal | None
    cadorim_rate: Decimal | None
