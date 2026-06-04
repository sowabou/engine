from datetime import date

import httpx


class WalletAPIClient:
    def __init__(self, base_url: str, api_key: str):
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def get_orders(self, from_date: date, status: str = "completed") -> list[dict]:
        response = await self.client.get(
            "/api/orders", params={"from_date": from_date.isoformat(), "status": status},
        )
        response.raise_for_status()
        return response.json()

    async def get_devises_transactions(self, from_date: date) -> list[dict]:
        response = await self.client.get(
            "/api/transactions/devises", params={"from_date": from_date.isoformat()},
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
