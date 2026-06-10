from __future__ import annotations

import math
import random
import statistics
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional, Tuple

from .models import OrderRequest


@dataclass
class SymbolState:
    symbol: str
    name: str
    price: float
    open_price: float
    volatility_bps: float
    volume: int
    bids: List[Tuple[float, int]] = field(default_factory=list)
    asks: List[Tuple[float, int]] = field(default_factory=list)

    @property
    def change_percent(self) -> float:
        return ((self.price - self.open_price) / self.open_price) * 100


@dataclass
class Position:
    symbol: str
    quantity: int
    avg_cost: float
    realized_pnl: float = 0.0

    def apply_fill(self, side: str, quantity: int, price: float) -> None:
        signed_quantity = quantity if side == "BUY" else -quantity

        if self.quantity == 0 or (self.quantity > 0 and signed_quantity > 0) or (
            self.quantity < 0 and signed_quantity < 0
        ):
            new_quantity = self.quantity + signed_quantity
            total_cost = abs(self.quantity) * self.avg_cost + quantity * price
            self.quantity = new_quantity
            self.avg_cost = total_cost / abs(new_quantity)
            return

        closing_quantity = min(abs(self.quantity), quantity)
        if self.quantity > 0:
            self.realized_pnl += (price - self.avg_cost) * closing_quantity
        else:
            self.realized_pnl += (self.avg_cost - price) * closing_quantity

        new_quantity = self.quantity + signed_quantity
        if new_quantity == 0:
            self.quantity = 0
            self.avg_cost = 0.0
        elif (self.quantity > 0 and new_quantity < 0) or (self.quantity < 0 and new_quantity > 0):
            self.quantity = new_quantity
            self.avg_cost = price
        else:
            self.quantity = new_quantity


class TradingSimulator:
    def __init__(self) -> None:
        self.rng = random.Random(20260610)
        self.symbols: Dict[str, SymbolState] = {
            "AAPL": SymbolState("AAPL", "Apple", 203.18, 200.75, 9.5, 18_450_000),
            "AMZN": SymbolState("AMZN", "Amazon", 183.42, 181.85, 10.5, 24_880_000),
            "NFLX": SymbolState("NFLX", "Netflix", 656.28, 648.10, 12.0, 4_220_000),
            "TSLA": SymbolState("TSLA", "Tesla", 249.87, 255.20, 18.0, 31_760_000),
        }
        self.cash = 250_000.0
        self.positions: Dict[str, Position] = {
            "AAPL": Position("AAPL", 120, 191.60),
            "AMZN": Position("AMZN", 75, 172.20),
            "NFLX": Position("NFLX", 30, 621.40),
            "TSLA": Position("TSLA", 50, 262.80),
        }
        self.open_orders: Dict[str, Dict[str, object]] = {}
        self.recent_orders: Deque[Dict[str, object]] = deque(maxlen=24)
        self.recent_fills: Deque[Dict[str, object]] = deque(maxlen=18)
        self.pnl_series: Deque[Dict[str, object]] = deque(maxlen=160)
        self.deduped_orders: Dict[str, Dict[str, object]] = {}
        self.sequence = 0
        self.event_counter = 0
        self.events_per_second = 100_000
        self.last_tick = time.monotonic()
        self.last_rate_window = self.last_tick
        self.window_events = 0
        self.starting_equity = self._equity(mark_to_market=False)

        for symbol in self.symbols.values():
            self._refresh_book(symbol)
        self._append_pnl_point()

    def snapshot(self, selected_symbol: str = "AAPL") -> Dict[str, object]:
        symbol = selected_symbol.upper()
        if symbol not in self.symbols:
            symbol = "AAPL"

        self._advance_market()
        equity = self._equity()
        exposure = self._gross_exposure()
        risk = self._risk_metrics(equity, exposure)
        positions = [self._position_payload(position) for position in self.positions.values()]
        positions.sort(key=lambda row: row["notional"], reverse=True)

        selected = self.symbols[symbol]
        best_bid = selected.bids[0][0]
        best_ask = selected.asks[0][0]

        return {
            "kind": "snapshot",
            "timestamp": self._now(),
            "sequence": self.sequence,
            "selected_symbol": symbol,
            "market": {
                "status": "OPEN",
                "events_per_second": self.events_per_second,
                "ui_latency_ms": round(self.rng.uniform(4.2, 9.8), 2),
                "match_latency_us": round(self.rng.uniform(180, 740), 1),
                "broker_lag_ms": round(self.rng.uniform(0.8, 4.5), 2),
                "event_log_offset": self.event_counter,
            },
            "symbols": [self._symbol_payload(item) for item in self.symbols.values()],
            "order_book": {
                "symbol": symbol,
                "spread": round(best_ask - best_bid, 4),
                "bids": [{"price": price, "size": size} for price, size in selected.bids],
                "asks": [{"price": price, "size": size} for price, size in selected.asks],
            },
            "portfolio": {
                "cash": round(self.cash, 2),
                "equity": round(equity, 2),
                "day_pnl": round(equity - self.starting_equity, 2),
                "day_pnl_percent": round(((equity - self.starting_equity) / self.starting_equity) * 100, 3),
                "positions": positions,
            },
            "risk": risk,
            "pnl_series": list(self.pnl_series),
            "open_orders": list(self.open_orders.values())[-10:],
            "recent_orders": list(self.recent_orders)[:10],
            "recent_fills": list(self.recent_fills)[:10],
        }

    def submit_order(self, request: OrderRequest) -> Dict[str, object]:
        symbol = request.symbol.upper()
        client_order_id = request.client_order_id
        if client_order_id and client_order_id in self.deduped_orders:
            return self.deduped_orders[client_order_id]

        if symbol not in self.symbols:
            return {"accepted": False, "reason": "Unknown symbol", "order": None, "fill": None}

        if request.order_type == "LIMIT" and request.price is None:
            return {"accepted": False, "reason": "Limit orders require a price", "order": None, "fill": None}

        price_basis = request.price or self._best_execution_price(symbol, request.side)
        risk_error = self._risk_check(symbol, request.side, request.quantity, price_basis)
        if risk_error:
            return {"accepted": False, "reason": risk_error, "order": None, "fill": None}

        order = {
            "id": f"ORD-{uuid.uuid4().hex[:8].upper()}",
            "client_order_id": client_order_id,
            "symbol": symbol,
            "side": request.side,
            "order_type": request.order_type,
            "quantity": request.quantity,
            "remaining_quantity": request.quantity,
            "price": round(request.price, 2) if request.price is not None else None,
            "status": "OPEN",
            "created_at": self._now(),
        }

        fill = self._try_execute(order)
        if fill:
            order["status"] = "FILLED"
            order["remaining_quantity"] = 0
        else:
            self.open_orders[str(order["id"])] = order

        self.recent_orders.appendleft(order.copy())
        response = {"accepted": True, "reason": None, "order": order, "fill": fill}
        if client_order_id:
            self.deduped_orders[client_order_id] = response
        return response

    def _advance_market(self) -> None:
        now = time.monotonic()
        elapsed = max(now - self.last_tick, 0.05)
        self.last_tick = now
        self.sequence += 1

        simulated_events = int(elapsed * self.rng.randint(96_000, 128_000))
        self.event_counter += simulated_events
        self.window_events += simulated_events
        if now - self.last_rate_window >= 1:
            self.events_per_second = int(self.window_events / (now - self.last_rate_window))
            self.window_events = 0
            self.last_rate_window = now

        for symbol in self.symbols.values():
            shock_bps = self.rng.gauss(0, symbol.volatility_bps)
            mean_reversion_bps = (symbol.open_price - symbol.price) / symbol.open_price * 1.8
            move = (shock_bps + mean_reversion_bps) / 10_000
            symbol.price = max(1.0, symbol.price * (1 + move))
            symbol.volume += self.rng.randint(3_000, 38_000)
            self._refresh_book(symbol)

        self._match_resting_orders()
        self._append_pnl_point()

    def _refresh_book(self, symbol: SymbolState) -> None:
        spread = max(0.02, symbol.price * (0.00035 + symbol.volatility_bps / 1_000_000))
        tick = max(0.01, symbol.price * 0.00018)
        bids: List[Tuple[float, int]] = []
        asks: List[Tuple[float, int]] = []

        for level in range(10):
            level_width = spread / 2 + level * tick
            base_size = 120 + level * 35
            bid_size = base_size + self.rng.randint(0, 420)
            ask_size = base_size + self.rng.randint(0, 420)
            bids.append((round(symbol.price - level_width, 2), bid_size))
            asks.append((round(symbol.price + level_width, 2), ask_size))

        symbol.bids = bids
        symbol.asks = asks

    def _try_execute(self, order: Dict[str, object]) -> Optional[Dict[str, object]]:
        symbol = str(order["symbol"])
        side = str(order["side"])
        order_type = str(order["order_type"])
        limit_price = order["price"]
        best_price = self._best_execution_price(symbol, side)

        crosses = order_type == "MARKET"
        if order_type == "LIMIT" and isinstance(limit_price, (float, int)):
            crosses = limit_price >= best_price if side == "BUY" else limit_price <= best_price

        if not crosses:
            return None

        fill_price = round(best_price, 2)
        quantity = int(order["quantity"])
        self._apply_fill(symbol, side, quantity, fill_price)
        fill = {
            "id": f"FIL-{uuid.uuid4().hex[:8].upper()}",
            "order_id": order["id"],
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": fill_price,
            "notional": round(quantity * fill_price, 2),
            "created_at": self._now(),
        }
        self.recent_fills.appendleft(fill)
        return fill

    def _match_resting_orders(self) -> None:
        filled_order_ids: List[str] = []
        for order_id, order in list(self.open_orders.items()):
            fill = self._try_execute(order)
            if fill:
                order["status"] = "FILLED"
                order["remaining_quantity"] = 0
                filled_order_ids.append(order_id)
                self.recent_orders.appendleft(order.copy())

        for order_id in filled_order_ids:
            self.open_orders.pop(order_id, None)

    def _apply_fill(self, symbol: str, side: str, quantity: int, price: float) -> None:
        cash_delta = quantity * price
        self.cash += -cash_delta if side == "BUY" else cash_delta
        position = self.positions.setdefault(symbol, Position(symbol, 0, 0.0))
        position.apply_fill(side, quantity, price)

    def _best_execution_price(self, symbol: str, side: str) -> float:
        book = self.symbols[symbol]
        return book.asks[0][0] if side == "BUY" else book.bids[0][0]

    def _risk_check(self, symbol: str, side: str, quantity: int, price: float) -> Optional[str]:
        notional = quantity * price
        equity = self._equity()
        current_position = self.positions.get(symbol, Position(symbol, 0, 0.0)).quantity
        signed_quantity = quantity if side == "BUY" else -quantity
        projected_position = current_position + signed_quantity
        projected_gross = self._gross_exposure() + abs(signed_quantity * price)

        if notional > 150_000:
            return "Order notional exceeds the $150K single-order limit"
        if side == "BUY" and notional > self.cash * 0.95:
            return "Insufficient cash after buying-power check"
        if abs(projected_position) > 1_000:
            return "Projected symbol position exceeds 1,000 shares"
        if projected_gross > equity * 2.5:
            return "Projected gross exposure exceeds 2.5x equity"
        return None

    def _position_payload(self, position: Position) -> Dict[str, object]:
        symbol = self.symbols[position.symbol]
        market_value = position.quantity * symbol.price
        unrealized = position.quantity * (symbol.price - position.avg_cost)
        return {
            "symbol": position.symbol,
            "quantity": position.quantity,
            "avg_cost": round(position.avg_cost, 2),
            "last_price": round(symbol.price, 2),
            "notional": round(abs(market_value), 2),
            "market_value": round(market_value, 2),
            "unrealized_pnl": round(unrealized, 2),
            "realized_pnl": round(position.realized_pnl, 2),
            "pnl_percent": round((unrealized / max(abs(position.avg_cost * position.quantity), 1)) * 100, 2),
        }

    def _symbol_payload(self, symbol: SymbolState) -> Dict[str, object]:
        return {
            "symbol": symbol.symbol,
            "name": symbol.name,
            "price": round(symbol.price, 2),
            "change_percent": round(symbol.change_percent, 3),
            "volume": symbol.volume,
            "bid": symbol.bids[0][0],
            "ask": symbol.asks[0][0],
        }

    def _risk_metrics(self, equity: float, exposure: float) -> Dict[str, object]:
        values = [float(point["equity"]) for point in self.pnl_series]
        returns = []
        for previous, current in zip(values, values[1:]):
            if previous:
                returns.append((current - previous) / previous)

        if len(returns) >= 2:
            mean_return = statistics.fmean(returns)
            std_return = statistics.pstdev(returns) or 0.000001
            value_at_risk = 1.65 * std_return * equity
            sharpe = (mean_return / std_return) * math.sqrt(252 * 390)
        else:
            value_at_risk = 0.0
            sharpe = 0.0

        max_equity = max(values) if values else equity
        min_after_peak = equity
        peak = values[0] if values else equity
        max_drawdown = 0.0
        for value in values:
            peak = max(peak, value)
            min_after_peak = min(min_after_peak, value)
            max_drawdown = min(max_drawdown, (value - peak) / peak if peak else 0.0)

        largest_position = 0.0
        for position in self.positions.values():
            largest_position = max(largest_position, abs(position.quantity * self.symbols[position.symbol].price))

        return {
            "gross_exposure": round(exposure, 2),
            "net_liquidation": round(equity, 2),
            "var_95": round(value_at_risk, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown_percent": round(max_drawdown * 100, 2),
            "concentration_percent": round((largest_position / exposure) * 100 if exposure else 0, 2),
            "buying_power": round(max(self.cash * 0.95, 0), 2),
        }

    def _append_pnl_point(self) -> None:
        equity = self._equity()
        self.pnl_series.append(
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "equity": round(equity, 2),
                "pnl": round(equity - self.starting_equity, 2),
            }
        )

    def _equity(self, mark_to_market: bool = True) -> float:
        equity = self.cash
        for position in self.positions.values():
            price = self.symbols[position.symbol].price if mark_to_market else position.avg_cost
            equity += position.quantity * price
        return equity

    def _gross_exposure(self) -> float:
        return sum(abs(position.quantity * self.symbols[position.symbol].price) for position in self.positions.values())

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
