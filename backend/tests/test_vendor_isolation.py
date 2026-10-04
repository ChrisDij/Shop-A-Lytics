def test_location_search_returns_only_the_current_vendor(client):
    response = client.get("/api/search?q=Campus")

    assert response.status_code == 200
    assert [item["name"] for item in response.get_json()["results"]] == [
        "Campus Cafe"
    ]


def test_query_parameter_cannot_change_vendor_scope(client):
    response = client.get("/api/search?q=Other&vendor_id=2")

    assert response.status_code == 200
    assert response.get_json()["results"] == []


def test_analytics_routes_require_authentication_or_demo_scope(app):
    app.config["DEMO_VENDOR_ID"] = None

    response = app.test_client().get("/api/alerts")

    assert response.status_code == 401
