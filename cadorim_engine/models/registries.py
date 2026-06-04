from sqlalchemy import BigInteger, Column, DateTime, Integer, String, func
from cadorim_engine.database import Base


class Partner(Base):
    """Par_l — partner/source registry. 7 values spanning 5 business flows."""

    __tablename__ = "partners"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    flow_type = Column(String, nullable=False)
    api_partner_name = Column(String, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, server_default=func.now())


class Bank(Base):
    """Bank_t — settlement bank/account registry."""

    __tablename__ = "banks"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    api_bank_account_id = Column(BigInteger, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, server_default=func.now())


class LocalPartner(Base):
    """Local_Par_n — payout channel registry."""

    __tablename__ = "local_partners"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    api_account_id = Column(BigInteger, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, server_default=func.now())


class Currency(Base):
    """Cur_k — currency registry."""

    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String, nullable=False)
    decimals = Column(Integer, default=2)
    created_at = Column(DateTime, server_default=func.now())
