from app.database import PersistenceStore
from app.models import OrderRequest
from app.simulator import TradingSimulator


def make_store(tmp_path):
    return PersistenceStore(f"sqlite:///{tmp_path / 'trading.db'}")


def test_market_order_persists_position_and_fill(tmp_path) -> None:
    store = make_store(tmp_path)
    simulator = TradingSimulator(persistence=store)

    before = simulator.positions["AAPL"].quantity
    result = simulator.submit_order(
        OrderRequest(symbol="AAPL", side="BUY", order_type="MARKET", quantity=7, client_order_id="persist-1")
    )
    assert result["accepted"] is True

    restarted = TradingSimulator(persistence=store)
    assert restarted.positions["AAPL"].quantity == before + 7
    assert len(restarted.recent_fills) == 1
    assert restarted.recent_fills[0]["order_id"] == result["order"]["id"]


def test_client_order_id_is_idempotent_after_restart(tmp_path) -> None:
    store = make_store(tmp_path)
    request = OrderRequest(symbol="TSLA", side="SELL", order_type="MARKET", quantity=2, client_order_id="restart-dup")

    first = TradingSimulator(persistence=store).submit_order(request)
    second = TradingSimulator(persistence=store).submit_order(request)

    assert first["accepted"] is True
    assert second["accepted"] is True
    assert first["order"]["id"] == second["order"]["id"]


def test_open_limit_order_survives_restart(tmp_path) -> None:
    store = make_store(tmp_path)
    simulator = TradingSimulator(persistence=store)

    result = simulator.submit_order(
        OrderRequest(symbol="AAPL", side="BUY", order_type="LIMIT", quantity=5, price=1.0, client_order_id="open-1")
    )

    assert result["accepted"] is True
    assert result["order"]["status"] == "OPEN"

    restarted = TradingSimulator(persistence=store)
    assert result["order"]["id"] in restarted.open_orders
