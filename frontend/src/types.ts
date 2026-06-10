export type Side = 'BUY' | 'SELL'
export type OrderType = 'MARKET' | 'LIMIT'

export interface SymbolQuote {
  symbol: string
  name: string
  price: number
  change_percent: number
  volume: number
  bid: number
  ask: number
}

export interface BookLevel {
  price: number
  size: number
}

export interface Position {
  symbol: string
  quantity: number
  avg_cost: number
  last_price: number
  notional: number
  market_value: number
  unrealized_pnl: number
  realized_pnl: number
  pnl_percent: number
}

export interface Fill {
  id: string
  order_id: string
  symbol: string
  side: Side
  quantity: number
  price: number
  notional: number
  created_at: string
}

export interface Order {
  id: string
  client_order_id?: string
  symbol: string
  side: Side
  order_type: OrderType
  quantity: number
  remaining_quantity: number
  price: number | null
  status: string
  created_at: string
}

export interface PnlPoint {
  time: string
  equity: number
  pnl: number
}

export interface MarketSnapshot {
  kind: 'snapshot'
  timestamp: string
  sequence: number
  selected_symbol: string
  market: {
    status: string
    events_per_second: number
    ui_latency_ms: number
    match_latency_us: number
    broker_lag_ms: number
    event_log_offset: number
  }
  symbols: SymbolQuote[]
  order_book: {
    symbol: string
    spread: number
    bids: BookLevel[]
    asks: BookLevel[]
  }
  portfolio: {
    cash: number
    equity: number
    day_pnl: number
    day_pnl_percent: number
    positions: Position[]
  }
  risk: {
    gross_exposure: number
    net_liquidation: number
    var_95: number
    sharpe: number
    max_drawdown_percent: number
    concentration_percent: number
    buying_power: number
  }
  pnl_series: PnlPoint[]
  open_orders: Order[]
  recent_orders: Order[]
  recent_fills: Fill[]
}

export interface OrderResponse {
  accepted: boolean
  reason: string | null
  order: Order | null
  fill: Fill | null
}
