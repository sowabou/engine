from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from cadorim_engine.database import Base


class PartnerCurrency(Base):
    """Config(Par_l, Cur_k) — commission parameters per partner per currency."""

    __tablename__ = "partner_currencies"

    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    commission_rate = Column(Numeric(8, 4), nullable=True)
    commission_type = Column(String, default="percentage")
    commission_fixed = Column(Numeric(15, 2), nullable=True)
    status = Column(String, default="active")

    __table_args__ = (UniqueConstraint("partner_id", "currency_id"),)


class PartnerBank(Base):
    """Config(Par_l, Bank_t) — settlement routing."""

    __tablename__ = "partner_banks"

    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    bank_id = Column(Integer, ForeignKey("banks.id"), nullable=False)
    status = Column(String, default="active")

    __table_args__ = (UniqueConstraint("partner_id", "bank_id"),)


class PartnerLocalPartner(Base):
    """Config(Par_l, Local_Par_n) — payout cost per partner per channel."""

    __tablename__ = "partner_local_partners"

    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    local_partner_id = Column(Integer, ForeignKey("local_partners.id"), nullable=False)
    payout_cost = Column(Numeric(15, 2), default=0)
    payout_cost_type = Column(String, default="fixed")
    status = Column(String, default="active")

    __table_args__ = (UniqueConstraint("partner_id", "local_partner_id"),)


class FxRate(Base):
    """FX(Par_l, Cur_k, date) — exchange rates."""

    __tablename__ = "fx_rates"

    id = Column(Integer, primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=False)
    date = Column(Date, nullable=False)
    partner_rate = Column(Numeric(12, 6), nullable=False)
    market_rate = Column(Numeric(12, 6), nullable=True)
    cadorim_rate = Column(Numeric(12, 6), nullable=True)

    __table_args__ = (UniqueConstraint("partner_id", "currency_id", "date"),)
