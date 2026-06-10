import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .database import PersistenceStore
from .models import OrderRequest, SymbolSelection
from .simulator import TradingSimulator


app = FastAPI(title="Real-Time Trading Dashboard API", version="0.1.0")
simulator = TradingSimulator(persistence=PersistenceStore.from_env())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "trading-dashboard-api",
        "persistence": "database" if simulator.persistence else "memory",
    }


@app.get("/api/snapshot")
def snapshot(symbol: str = "AAPL") -> dict:
    return simulator.snapshot(symbol)


@app.post("/api/orders")
def submit_order(order: OrderRequest) -> dict:
    return simulator.submit_order(order)


@app.post("/api/symbol")
def select_symbol(selection: SymbolSelection) -> dict:
    return simulator.snapshot(selection.symbol)


@app.websocket("/ws/market")
async def market_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    selected_symbol = websocket.query_params.get("symbol", "AAPL").upper()

    try:
        while True:
            await websocket.send_json(simulator.snapshot(selected_symbol))
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=0.25)
            except asyncio.TimeoutError:
                continue

            if message.get("type") == "select_symbol":
                selected_symbol = str(message.get("symbol", selected_symbol)).upper()
    except WebSocketDisconnect:
        return
