"""Tests for engine/controls.py."""
from datetime import datetime
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from cadorim_engine.database import Base
from cadorim_engine.engine.controls import validate_transaction
from cadorim_engine.models.computed import EngineTransaction
import cadorim_engine.models  # noqa


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        yield s
    await engine.dispose()


def _tx(**overrides):
    base = {
        "source_table": "wallet_db_transactions", "source_id": 1,
        "source_reference": "REF001", "date": datetime(2026, 4, 17),
        "flow_type": "international_remittance", "db_type": "ria",
        "partner_id": 1, "currency_id": 1,
        "amount_original": Decimal("100"), "amount_mru": Decimal("3950"),
        "fx_rate": Decimal("39.5"), "status": "completed",
    }
    base.update(overrides)
    return base


async def test_valid_transaction(session):
    errors = await validate_transaction(_tx(), session)
    assert errors == []


async def test_duplicate(session):
    session.add(EngineTransaction(**{
        **_tx(), "commission_a": 0, "cost_payout_a": 0, "gain_transaction_a": 0,
        "fx_gain_a": 0, "profit_transaction_a": 0,
    }))
    await session.commit()
    errors = await validate_transaction(_tx(source_id=1), session)
    assert any("DUPLICATE" in e for e in errors)


async def test_amount_mismatch(session):
    errors = await validate_transaction(_tx(amount_mru=Decimal("5000")), session)
    assert any("AMOUNT_MISMATCH" in e for e in errors)


async def test_no_mismatch_within_tolerance(session):
    errors = await validate_transaction(_tx(amount_mru=Decimal("3950.50")), session)
    assert not any("AMOUNT_MISMATCH" in e for e in errors)
