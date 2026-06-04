from fastapi import FastAPI
from cadorim_engine.api.routes.registries import router as registries_router
from cadorim_engine.api.routes.configurations import router as configurations_router
from cadorim_engine.api.routes.transactions import router as transactions_router
from cadorim_engine.api.routes.settlements import router as settlements_router
from cadorim_engine.api.routes.dashboards import router as dashboards_router

app = FastAPI(
    title="Cadorim Accounting Engine v2",
    version="2.0.0",
    description="Universal parameter-driven transaction engine — all 5 business flows.",
)

app.include_router(registries_router)
app.include_router(configurations_router)
app.include_router(transactions_router)
app.include_router(settlements_router)
app.include_router(dashboards_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
