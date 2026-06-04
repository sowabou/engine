from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


# ── Shared building blocks ───────────────────────────────────────────────


class PeriodFilter(BaseModel):
    """Query filter shared across all dashboards."""
    start_date: date
    end_date: date
    partner_id: int | None = None
    currency_id: int | None = None


class PartnerSummary(BaseModel):
    partner_id: int
    partner_code: str
    partner_name: str
    flow_type: str
    transaction_count: int
    volume_mru: Decimal
    commission: Decimal
    profit: Decimal


class CurrencySummary(BaseModel):
    currency_id: int
    currency_code: str
    transaction_count: int
    volume_original: Decimal
    volume_mru: Decimal


class DailySummary(BaseModel):
    date: date
    transaction_count: int
    volume_mru: Decimal
    profit: Decimal


class FlowSummary(BaseModel):
    flow_type: str
    transaction_count: int
    volume_mru: Decimal
    commission: Decimal
    profit: Decimal


# ── CEO Dashboard ────────────────────────────────────────────────────────


class CEODashboard(BaseModel):
    """High-level P&L view for executive oversight."""

    period_start: date
    period_end: date

    total_transactions: int
    total_volume_mru: Decimal
    total_commission: Decimal
    total_payout_cost: Decimal
    total_fx_gain: Decimal
    total_profit: Decimal

    by_flow: list[FlowSummary]
    by_partner: list[PartnerSummary]
    daily_trend: list[DailySummary]


# ── Operations Dashboard ────────────────────────────────────────────────


class StatusBreakdown(BaseModel):
    status: str
    count: int
    volume_mru: Decimal


class LocalPartnerVolume(BaseModel):
    local_partner_id: int
    local_partner_code: str
    transaction_count: int
    volume_mru: Decimal
    payout_cost: Decimal


class OperationsDashboard(BaseModel):
    """Transaction processing and payout monitoring."""

    period_start: date
    period_end: date

    total_transactions: int
    total_volume_mru: Decimal

    by_status: list[StatusBreakdown]
    by_flow: list[FlowSummary]
    by_currency: list[CurrencySummary]
    by_local_partner: list[LocalPartnerVolume]
    daily_trend: list[DailySummary]


# ── Treasury Dashboard ──────────────────────────────────────────────────


class SettlementSummary(BaseModel):
    partner_id: int
    partner_code: str
    bank_id: int
    bank_code: str
    currency_code: str
    total_settled: Decimal
    total_converted: Decimal
    gain_sett: Decimal
    settlement_count: int


class UnsettledPosition(BaseModel):
    partner_id: int
    partner_code: str
    currency_code: str
    unsettled_volume_mru: Decimal
    transaction_count: int


class FxSnapshot(BaseModel):
    partner_id: int
    partner_code: str
    currency_code: str
    date: date
    partner_rate: Decimal
    market_rate: Decimal | None
    cadorim_rate: Decimal | None


class TreasuryDashboard(BaseModel):
    """Settlement tracking and FX position monitoring."""

    period_start: date
    period_end: date

    total_settled_mru: Decimal
    total_gain_sett: Decimal

    settlements: list[SettlementSummary]
    unsettled_positions: list[UnsettledPosition]
    latest_fx_rates: list[FxSnapshot]
