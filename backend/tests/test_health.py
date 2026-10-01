def test_health_endpoint(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "service": "shop-a-lytics-api",
        "status": "ok",
    }


def test_contract_placeholder(client):
    response = client.get("/api/summary")

    assert response.status_code == 501
    assert "not implemented" in response.get_json()["error"].lower()

