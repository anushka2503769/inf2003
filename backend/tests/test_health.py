import asyncio

import httpx

from app.main import app


def request(path: str) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(send())


def test_health_contract():
    response = request("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "jobless-simulator-api"}


def test_unknown_route_is_not_a_success():
    assert request("/api/not-a-route").status_code == 404
