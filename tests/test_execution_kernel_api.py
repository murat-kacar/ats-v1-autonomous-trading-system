from ats_execution_kernel.main import app
from fastapi.testclient import TestClient


def test_execution_simulate_endpoint_returns_report() -> None:
    client = TestClient(app)

    payload = {
        "request_id": "ex-api-1",
        "intent": {
            "request_id": "ex-api-1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": 0.02,
            "maker_preferred": True,
        },
        "reference_price": 100000.0,
        "order_size_usd": 1000.0,
        "mode": "NORMAL",
        "reduce_only": False,
        "liquidity": {
            "spread_bps": 3.5,
            "depth_1pct_usd": 30000.0,
            "expected_impact_bps": 4.0,
        },
        "rolling_1m_vol_pct": 0.5,
        "one_minute_move_pct": 0.9,
        "avg_fill_time_seconds": 6.0,
        "elapsed_unwind_seconds": 0.0,
        "commission_bps": 2.0,
        "slippage_bps": 1.0,
        "funding_bps": 0.2,
        "impact_bps": 0.7,
        "requested_kill_switch": False,
    }

    response = client.post("/v1/execution/simulate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["accepted"] is True
    assert body["report"]["reason_codes"] == ["OK"]
    assert body["liquidity_gate_passed"] is True
