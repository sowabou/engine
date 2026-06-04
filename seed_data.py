"""Seed script — populates registries and configurations. Idempotent.
Usage: python seed_data.py
"""
import asyncio
from decimal import Decimal
from sqlalchemy import select
from cadorim_engine.database import async_session, engine as db_engine, Base
from cadorim_engine.models.registries import Partner, Bank, LocalPartner, Currency
from cadorim_engine.models.configurations import PartnerCurrency, PartnerBank, PartnerLocalPartner
import cadorim_engine.models  # noqa

PARTNERS = [
    {"code": "ria", "name": "Ria Money Transfer", "flow_type": "international", "api_partner_name": None},
    {"code": "terrapay", "name": "TerraPay", "flow_type": "international", "api_partner_name": "terrapay"},
    {"code": "juba", "name": "Juba Express", "flow_type": "international", "api_partner_name": None},
    {"code": "cadorim_wallet", "name": "Cadorim Wallet (MauriPay)", "flow_type": "wallet", "api_partner_name": "mauripay"},
    {"code": "cadorim_b2c", "name": "CadorimPay (B2C)", "flow_type": "b2c", "api_partner_name": None},
    {"code": "cadorim_agent", "name": "Cadorim Agent Network", "flow_type": "agent", "api_partner_name": "cadorim-agent"},
    {"code": "treasury", "name": "Treasury / Internal", "flow_type": "treasury", "api_partner_name": None},
]
BANKS = [
    {"code": "bmi", "name": "BMI", "currency": "EUR"},
    {"code": "bpm", "name": "BPM", "currency": "EUR"},
    {"code": "bred", "name": "BRED", "currency": "EUR"},
    {"code": "eth_cado01", "name": "ETH Cado01", "currency": "USDC"},
    {"code": "eth_cado02", "name": "ETH Cado02", "currency": "USDC"},
]
LOCAL_PARTNERS = [
    {"code": "sedad", "name": "Sedad", "type": "wallet", "api_account_id": 16},
    {"code": "click", "name": "Click", "type": "wallet", "api_account_id": 20},
    {"code": "masrvi", "name": "Masrvi", "type": "wallet", "api_account_id": 21},
    {"code": "bankily", "name": "Bankily", "type": "wallet", "api_account_id": 825},
    {"code": "mauripay", "name": "MauriPay", "type": "wallet"},
    {"code": "wallet_internal", "name": "Internal Wallet Transfer", "type": "internal"},
    {"code": "caisse_cadorim", "name": "Caisse Cadorim (Main)", "type": "cash", "api_account_id": 18},
    {"code": "caisse_imara", "name": "Caisse IMARA", "type": "cash", "api_account_id": 19},
    {"code": "caisse_mboirick", "name": "Caisse Mboirick/BMD", "type": "cash", "api_account_id": 33},
    {"code": "caisse_seilibaby", "name": "Caisse Seilibaby", "type": "cash", "api_account_id": 35},
]
CURRENCIES = [
    {"code": "EUR", "name": "Euro", "decimals": 2},
    {"code": "USD", "name": "US Dollar", "decimals": 2},
    {"code": "USDC", "name": "USD Coin", "decimals": 6},
    {"code": "MRU", "name": "Mauritanian Ouguiya", "decimals": 2},
]
PARTNER_CURRENCIES = [
    {"partner": "ria", "currency": "EUR", "rate": Decimal("0"), "type": "percentage"},
    {"partner": "terrapay", "currency": "USD", "rate": Decimal("0.005"), "type": "percentage"},
    {"partner": "terrapay", "currency": "USDC", "rate": Decimal("0.005"), "type": "percentage"},
    {"partner": "terrapay", "currency": "EUR", "rate": Decimal("0.005"), "type": "percentage"},
    {"partner": "juba", "currency": "EUR", "rate": Decimal("0.01"), "type": "percentage"},
    {"partner": "cadorim_wallet", "currency": "MRU", "rate": Decimal("0"), "type": "percentage"},
    {"partner": "cadorim_b2c", "currency": "MRU", "rate": Decimal("0"), "type": "percentage"},
    {"partner": "cadorim_agent", "currency": "MRU", "rate": Decimal("0"), "type": "percentage"},
    {"partner": "treasury", "currency": "MRU", "rate": Decimal("0"), "type": "percentage"},
]
PARTNER_BANKS = [
    {"partner": "ria", "bank": "bmi"}, {"partner": "ria", "bank": "bred"},
    {"partner": "terrapay", "bank": "bmi"}, {"partner": "terrapay", "bank": "eth_cado01"},
    {"partner": "terrapay", "bank": "eth_cado02"}, {"partner": "juba", "bank": "bpm"},
]

async def _upsert(session, cls, lookup, defaults=None):
    stmt = select(cls)
    for k, v in lookup.items():
        stmt = stmt.where(getattr(cls, k) == v)
    obj = (await session.execute(stmt)).scalar_one_or_none()
    if obj:
        return obj, False
    obj = cls(**{**lookup, **(defaults or {})})
    session.add(obj)
    await session.flush()
    return obj, True

async def seed():
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        pm = {}
        for p in PARTNERS:
            obj, new = await _upsert(session, Partner, {"code": p["code"]},
                                     {"name": p["name"], "flow_type": p["flow_type"], "api_partner_name": p["api_partner_name"]})
            pm[p["code"]] = obj
            print(f"  Partner {p['code']}: {'NEW' if new else 'exists'}")
        bm = {}
        for b in BANKS:
            obj, new = await _upsert(session, Bank, {"code": b["code"]}, {"name": b["name"], "currency": b["currency"]})
            bm[b["code"]] = obj
        lm = {}
        for lp in LOCAL_PARTNERS:
            obj, new = await _upsert(session, LocalPartner, {"code": lp["code"]},
                                     {"name": lp["name"], "type": lp["type"], "api_account_id": lp.get("api_account_id")})
            lm[lp["code"]] = obj
            print(f"  LocalPartner {lp['code']}: {'NEW' if new else 'exists'}")
        cm = {}
        for c in CURRENCIES:
            obj, _ = await _upsert(session, Currency, {"code": c["code"]}, {"name": c["name"], "decimals": c["decimals"]})
            cm[c["code"]] = obj
        await session.commit()
        for pc in PARTNER_CURRENCIES:
            await _upsert(session, PartnerCurrency,
                          {"partner_id": pm[pc["partner"]].id, "currency_id": cm[pc["currency"]].id},
                          {"commission_rate": pc["rate"], "commission_type": pc["type"]})
        for pb in PARTNER_BANKS:
            await _upsert(session, PartnerBank, {"partner_id": pm[pb["partner"]].id, "bank_id": bm[pb["bank"]].id})
        await session.commit()
        print("Seed complete.")

if __name__ == "__main__":
    asyncio.run(seed())
