from app.models import OrderRequest
from app.simulator import TradingSimulator


def test_market_order_fills_and_updates_position() -> None:
    simulator = TradingSimulator()
    before = simulator.positions["AAPL"].quantity

    result = simulator.submit_order(
        OrderRequest(symbol="AAPL", side="BUY", order_type="MARKET", quantity=10, client_order_id="unit-1")
    )

    assert result["accepted"] is True
    assert result["fill"] is not None
    assert simulator.positions["AAPL"].quantity == before + 10


def test_duplicate_client_order_id_is_idempotent() -> None:
    simulator = TradingSimulator()
    request = OrderRequest(symbol="TSLA", side="SELL", order_type="MARKET", quantity=3, client_order_id="dup-1")

    first = simulator.submit_order(request)
    second = simulator.submit_order(request)

    assert first["accepted"] is True
    assert first["order"]["id"] == second["order"]["id"]
    assert len(simulator.recent_fills) == 1


def test_risk_gate_rejects_oversized_notional() -> None:
    simulator = TradingSimulator()

    result = simulator.submit_order(OrderRequest(symbol="NFLX", side="BUY", order_type="MARKET", quantity=10_000))

    assert result["accepted"] is False
    assert "notional" in result["reason"]
