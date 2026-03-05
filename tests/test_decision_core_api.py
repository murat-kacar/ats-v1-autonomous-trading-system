from datetime import UTC, datetime

from ats_decision_core.main import app
from fastapi.testclient import TestClient


def test_decision_core_propose_endpoint() -> None:
    client = TestClient(app)

    payload = {
        "request_id": "req-api-1",
        "evidence": {
            "request_id": "req-api-1",
            "created_at": datetime(2026, 3, 5, 18, 10, tzinfo=UTC).isoformat(),
            "uncertainty_score": 0.30,
            "data_quality_score": 0.93,
            "feature_values": {
                "trend_direction": 0.40,
                "trend_confidence": 0.70,
                "mean_reversion_direction": -0.08,
                "mean_reversion_confidence": 0.45,
            },
            "risk_flags": ["SANITY_OK"],
            "source_reliability": {
                "trend": 0.76,
                "mean_reversion": 0.61,
            },
        },
        "candidates": [
            {
                "horizon": "15m",
                "window_days": 60,
                "sample_size": 250,
                "walk_forward_score": 1.2,
                "embargo_passed": True,
                "gross_edge_bps": 12.5,
                "fee_bps": 2.0,
                "slippage_bps": 1.0,
                "funding_bps": 0.4,
                "impact_bps": 0.7,
            }
        ],
    }

    response = client.post("/v1/decision/propose", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req-api-1"
    assert body["selected_horizon"] == "15m|60d"
    assert body["edge_bps_after_cost"] == 8.4
    assert body["reason_codes"] == ["OK"]
