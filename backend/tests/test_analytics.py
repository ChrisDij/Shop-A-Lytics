def test_meta_reports_dataset_readiness(client):
    response = client.get("/api/meta")

    assert response.status_code == 200
    result = response.get_json()
    assert result["ready"] is True
    assert result["history_days"] == 105
    assert result["vendors"] == 2


def test_alerts_identify_unusual_activity_without_accusatory_language(client):
    response = client.get("/api/alerts")

    assert response.status_code == 200
    result = response.get_json()
    assert result["status"] == "ready"
    assert result["alerts"]
    alert = result["alerts"][0]
    assert alert["kind"] == "spike"
    assert alert["actual_transactions"] == 30
    assert "requiring investigation" in alert["message"]
    assert "not evidence of fraud" in alert["message"]


def test_invalid_alert_limit_uses_safe_default(client):
    response = client.get("/api/alerts?limit=not-a-number")

    assert response.status_code == 200
    assert response.get_json()["alerts"]


def test_missing_database_returns_not_assessed(app):
    app.config["ANALYTICS_DB_PATH"] = "/file/that/does/not/exist.sqlite"

    response = app.test_client().get("/api/meta")

    assert response.status_code == 200
    result = response.get_json()
    assert result["ready"] is False
    assert result["status"] == "not_assessed"
