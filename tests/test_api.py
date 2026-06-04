"""API endpoint tests for v2."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from cadorim_engine.api.app import app
from cadorim_engine.database import get_session, Base
import cadorim_engine.models  # noqa


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override():
        async with test_session() as s:
            yield s
    app.dependency_overrides[get_session] = override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["version"] == "2.0.0"


async def test_partner_crud(client):
    r = await client.post("/engine/v1/partners", json={
        "code": "ria", "name": "Ria", "flow_type": "international"
    })
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["flow_type"] == "international"

    r = await client.get("/engine/v1/partners")
    assert len(r.json()) == 1

    r = await client.patch(f"/engine/v1/partners/{pid}", json={"name": "Ria Updated"})
    assert r.json()["name"] == "Ria Updated"


async def test_bank_crud(client):
    r = await client.post("/engine/v1/banks", json={"code": "bmi", "name": "BMI", "currency": "EUR"})
    assert r.status_code == 201


async def test_local_partner_crud(client):
    r = await client.post("/engine/v1/local-partners", json={"code": "sedad", "name": "Sedad", "type": "wallet"})
    assert r.status_code == 201
    assert r.json()["type"] == "wallet"


async def test_currency_crud(client):
    r = await client.post("/engine/v1/currencies", json={"code": "MRU", "name": "Ouguiya"})
    assert r.status_code == 201


async def test_config_partner_currency(client):
    await client.post("/engine/v1/partners", json={"code": "tp", "name": "TP", "flow_type": "international"})
    await client.post("/engine/v1/currencies", json={"code": "USD", "name": "Dollar"})
    r = await client.post("/engine/v1/config/partner-currencies", json={
        "partner_id": 1, "currency_id": 1, "commission_rate": "0.005", "commission_type": "percentage"
    })
    assert r.status_code == 201


async def test_fx_rate(client):
    await client.post("/engine/v1/partners", json={"code": "ria", "name": "Ria", "flow_type": "international"})
    await client.post("/engine/v1/currencies", json={"code": "EUR", "name": "Euro"})
    r = await client.post("/engine/v1/fx-rates", json={
        "partner_id": 1, "currency_id": 1, "date": "2026-04-17",
        "partner_rate": "39.5", "market_rate": "39.6", "cadorim_rate": "39.8"
    })
    assert r.status_code == 201


async def test_dashboards_empty(client):
    for endpoint in ["/engine/v1/dashboard/ceo", "/engine/v1/dashboard/operations", "/engine/v1/dashboard/treasury"]:
        r = await client.get(endpoint)
        assert r.status_code == 200


async def test_404(client):
    r = await client.get("/engine/v1/partners/999")
    assert r.status_code == 404


async def test_new_partner_zero_code_changes(client):
    """Adding a new partner requires ZERO code changes."""
    r = await client.post("/engine/v1/partners", json={"code": "worldremit", "name": "WorldRemit", "flow_type": "international"})
    assert r.status_code == 201
    r = await client.post("/engine/v1/currencies", json={"code": "GBP", "name": "Pound"})
    assert r.status_code == 201
    r = await client.post("/engine/v1/config/partner-currencies", json={
        "partner_id": 1, "currency_id": 1, "commission_rate": "0.0075", "commission_type": "percentage"
    })
    assert r.status_code == 201
    r = await client.get("/engine/v1/partners")
    assert any(p["code"] == "worldremit" for p in r.json())
