from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    res = client.get("/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_cors_allows_web_origin(client: TestClient) -> None:
    res = client.get("/v1/health", headers={"Origin": "http://localhost:3000"})
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_blocks_unknown_origin(client: TestClient) -> None:
    res = client.get("/v1/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in res.headers


def test_openapi_published(client: TestClient) -> None:
    assert client.get("/openapi.json").json()["info"]["title"].startswith("LETS")
