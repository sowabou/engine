from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


# ── EngineTransaction ────────────────────────────────────────────────────


class EngineTransactionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int

    # Source identification
    source_table: str
    source_id: int
    source_reference: str
    linked_order_id: int | None

    date: datetime

    # Classified flow
    flow_type: str
    db_type: str

    # Universal parameters
    partner_id: int
    currency_id: int
    local_partner_id: int | None

    # Accounts from wallet_db
    debit_account_id: int | None
    debit_account_type: str | None
    credit_account_id: int | None
    credit_account_type: str | None

    # Clients
    sender_name: str | None
    sender_phone: str | None
    receiver_name: str | None
    receiver_phone: str | None

    # Amounts
    amount_original: Decimal
    amount_mru: Decimal
    fx_rate: Decimal

    # Layer 1 — computed by engine
    commission_a: Decimal
    cost_payout_a: Decimal
    gain_transaction_a: Decimal
    fx_gain_a: Decimal
    profit_transaction_a: Decimal

    # Fees from source (reconciliation)
    source_frais: Decimal
    source_commission: Decimal

    # Status
    status: str
    settlement_status: str

    # Description
    description: str | None

    created_at: datetime | None


# ── EngineSettlement ─────────────────────────────────────────────────────


class EngineSettlementResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    partner_id: int
    bank_id: int
    currency_id: int
    date: date
    amount_original: Decimal
    amount_converted: Decimal | None
    settlement_rate: Decimal | None
    gain_sett: Decimal | None
    external_reference: str | None
    api_devises_id: int | None
    created_at: datetime | None
