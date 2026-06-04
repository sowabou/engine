from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship
from cadorim_engine.database import Base


class EngineTransaction(Base):
    """Engine's processed transaction — universal model with dual-source support.

    Every row traces back to source_table + source_id. The wallet_db_transactions
    journal is the master; partner_db_orders enriches with client names and FX data.
    """

    __tablename__ = "engine_transactions"

    id = Column(Integer, primary_key=True)

    # Source identification
    source_table = Column(String, nullable=False)
    source_id = Column(BigInteger, nullable=False)
    source_reference = Column(String, nullable=False)
    linked_order_id = Column(BigInteger, nullable=True)

    date = Column(DateTime, nullable=False)

    # Classified flow
    flow_type = Column(String, nullable=False)
    db_type = Column(String, nullable=False)

    # Universal parameters
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    local_partner_id = Column(Integer, ForeignKey("local_partners.id"), nullable=True)

    # Accounts from wallet_db
    debit_account_id = Column(BigInteger, nullable=True)
    debit_account_type = Column(String, nullable=True)
    credit_account_id = Column(BigInteger, nullable=True)
    credit_account_type = Column(String, nullable=True)

    # Clients
    sender_name = Column(String, nullable=True)
    sender_phone = Column(String, nullable=True)
    receiver_name = Column(String, nullable=True)
    receiver_phone = Column(String, nullable=True)

    # Amounts
    amount_original = Column(Numeric(15, 2), nullable=False)
    amount_mru = Column(Numeric(15, 2), nullable=False)
    fx_rate = Column(Numeric(12, 6), default=0)

    # Layer 1 — computed by engine
    commission_a = Column(Numeric(15, 2), default=0)
    cost_payout_a = Column(Numeric(15, 2), default=0)
    gain_transaction_a = Column(Numeric(15, 2), default=0)
    fx_gain_a = Column(Numeric(15, 2), default=0)
    profit_transaction_a = Column(Numeric(15, 2), default=0)

    # Fees from source (reconciliation)
    source_frais = Column(Numeric(15, 2), default=0)
    source_commission = Column(Numeric(15, 2), default=0)

    # Status
    status = Column(String, nullable=False)
    settlement_status = Column(String, default="unsettled")

    # Description
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("source_table", "source_id"),
    )

    # Relationships
    partner = relationship("Partner")
    currency = relationship("Currency")
    local_partner = relationship("LocalPartner")


class EngineSettlement(Base):
    """Engine's settlement events — Layer 2 gain computation."""

    __tablename__ = "engine_settlements"

    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    bank_id = Column(Integer, ForeignKey("banks.id"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    date = Column(Date, nullable=False)
    amount_original = Column(Numeric(15, 2), nullable=False)
    amount_converted = Column(Numeric(15, 2), nullable=True)
    settlement_rate = Column(Numeric(12, 6), nullable=True)
    gain_sett = Column(Numeric(15, 2), nullable=True)
    external_reference = Column(String)
    api_devises_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    partner = relationship("Partner")
    bank = relationship("Bank")
    currency = relationship("Currency")
