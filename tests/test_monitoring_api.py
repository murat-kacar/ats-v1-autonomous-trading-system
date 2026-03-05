from ats_monitoring.main import app
from fastapi.testclient import TestClient


def test_monitoring_evaluate_endpoint() -> None:
    client = TestClient(app)

    payload = {
        "request_id": "m-api-1",
        "recent_trade_pnls": [0.6, 1.2, -0.2, 0.4, 1.0, -0.1],
        "baseline_pnl_mean": 0.5,
        "baseline_pnl_std": 0.4,
        "ci_coverage": 0.72,
        "brier_score": 0.12,
        "baseline_brier_score": 0.11,
    }

    response = client.post("/v1/monitoring/evaluate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "m-api-1"
    assert body["recommended_action"] in {"KEEP_LIVE", "REDUCE_LIVE_SIZE", "DEMOTE_TO_SHADOW"}
