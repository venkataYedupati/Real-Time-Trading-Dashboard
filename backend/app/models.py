from typing import Literal, Optional

from pydantic import BaseModel, Field


Side = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT"]


class OrderRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=8)
    side: Side
    order_type: OrderType = "MARKET"
    quantity: int = Field(..., gt=0, le=100_000)
    price: Optional[float] = Field(default=None, gt=0)
    client_order_id: Optional[str] = Field(default=None, max_length=64)


class SymbolSelection(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=8)
