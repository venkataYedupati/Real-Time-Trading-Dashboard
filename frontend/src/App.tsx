import type { FormEvent, ReactNode } from 'react'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  ArrowDown,
  ArrowUp,
  BarChart3,
  CircleDollarSign,
  Gauge,
  RadioTower,
  Send,
  ShieldCheck,
  Wifi,
  WifiOff,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useMarketStream } from './hooks/useMarketStream'
import { compact, currency, integer, percent, signedCurrency } from './lib/format'
import type { OrderResponse, OrderType, Side, SymbolQuote } from './types'

function App() {
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL')
  const [side, setSide] = useState<Side>('BUY')
  const [orderType, setOrderType] = useState<OrderType>('MARKET')
  const [quantity, setQuantity] = useState(25)
  const [limitPrice, setLimitPrice] = useState('')
  const [orderResponse, setOrderResponse] = useState<OrderResponse | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const { snapshot, connectionState } = useMarketStream(selectedSymbol)

  const selectedQuote = snapshot?.symbols.find((quote) => quote.symbol === selectedSymbol)
  const depthRows = useMemo(() => {
    if (!snapshot) return []
    return snapshot.order_book.bids.map((bid, index) => ({
      level: index + 1,
      bidPrice: bid.price,
      bidSize: bid.size,
      askPrice: snapshot.order_book.asks[index]?.price ?? 0,
      askSize: snapshot.order_book.asks[index]?.size ?? 0,
    }))
  }, [snapshot])

  async function submitOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setOrderResponse(null)

    const payload = {
      symbol: selectedSymbol,
      side,
      order_type: orderType,
      quantity,
      price: orderType === 'LIMIT' ? Number(limitPrice) : undefined,
      client_order_id:
        crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    }

    try {
      const response = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      setOrderResponse((await response.json()) as OrderResponse)
    } catch {
      setOrderResponse({
        accepted: false,
        reason: 'Order API is unreachable',
        order: null,
        fill: null,
      })
    } finally {
      setSubmitting(false)
    }
  }

  const isConnected = connectionState === 'connected'

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Trading Ops</p>
          <h1>Real-Time Trading Dashboard</h1>
        </div>
        <div className={`connection-pill ${isConnected ? 'connected' : 'disconnected'}`}>
          {isConnected ? <Wifi size={18} /> : <WifiOff size={18} />}
          <span>{connectionState}</span>
        </div>
      </header>

      <section className="metric-grid" aria-label="market metrics">
        <Metric icon={<RadioTower />} label="Feed rate" value={snapshot ? `${compact(snapshot.market.events_per_second)}/s` : '--'} />
        <Metric icon={<Gauge />} label="UI latency" value={snapshot ? `${snapshot.market.ui_latency_ms} ms` : '--'} />
        <Metric icon={<Activity />} label="Match latency" value={snapshot ? `${snapshot.market.match_latency_us} us` : '--'} />
        <Metric icon={<CircleDollarSign />} label="Equity" value={snapshot ? currency(snapshot.portfolio.equity, 0) : '--'} />
        <Metric
          icon={<BarChart3 />}
          label="Day P&L"
          value={snapshot ? signedCurrency(snapshot.portfolio.day_pnl) : '--'}
          tone={snapshot && snapshot.portfolio.day_pnl < 0 ? 'negative' : 'positive'}
        />
        <Metric icon={<ShieldCheck />} label="VaR 95" value={snapshot ? currency(snapshot.risk.var_95, 0) : '--'} />
      </section>

      <section className="symbol-strip" aria-label="symbols">
        {(snapshot?.symbols ?? seedQuotes).map((quote) => (
          <button
            type="button"
            className={`symbol-tile ${quote.symbol === selectedSymbol ? 'active' : ''}`}
            key={quote.symbol}
            onClick={() => {
              setSelectedSymbol(quote.symbol)
              setLimitPrice('')
            }}
          >
            <span className="symbol-name">{quote.symbol}</span>
            <strong>{currency(quote.price)}</strong>
            <span className={quote.change_percent >= 0 ? 'positive' : 'negative'}>
              {quote.change_percent >= 0 ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
              {percent(quote.change_percent, 2)}
            </span>
          </button>
        ))}
      </section>

      <section className="workspace-grid">
        <Panel
          className="book-panel"
          title={`${selectedSymbol} order book`}
          action={selectedQuote ? `${currency(selectedQuote.bid)} / ${currency(selectedQuote.ask)}` : '--'}
        >
          <ChartFrame className="chart-block">
            {({ width, height }) => (
              <BarChart width={width} height={height} data={depthRows}>
                <CartesianGrid stroke="#2d2d2d" vertical={false} />
                <XAxis dataKey="level" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} width={42} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                <Bar dataKey="bidSize" fill="#24d39b" radius={[4, 4, 0, 0]} />
                <Bar dataKey="askSize" fill="#ff6875" radius={[4, 4, 0, 0]} />
              </BarChart>
            )}
          </ChartFrame>
          <div className="book-table">
            <div className="book-head">
              <span>Bid</span>
              <span>Size</span>
              <span>Ask</span>
              <span>Size</span>
            </div>
            {depthRows.slice(0, 8).map((row) => (
              <div className="book-row" key={row.level}>
                <span className="positive">{currency(row.bidPrice)}</span>
                <span>{integer(row.bidSize)}</span>
                <span className="negative">{currency(row.askPrice)}</span>
                <span>{integer(row.askSize)}</span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel className="portfolio-panel" title="Portfolio P&L" action={snapshot ? percent(snapshot.portfolio.day_pnl_percent, 3) : '--'}>
          <ChartFrame className="pnl-chart">
            {({ width, height }) => (
              <AreaChart width={width} height={height} data={snapshot?.pnl_series ?? []}>
                <defs>
                  <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6ea8ff" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#6ea8ff" stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#2d2d2d" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis tickLine={false} axisLine={false} width={64} tickFormatter={(value) => compact(Number(value))} />
                <Tooltip contentStyle={tooltipStyle} formatter={(value) => currency(Number(value))} />
                <Area type="monotone" dataKey="equity" stroke="#6ea8ff" fill="url(#pnlFill)" strokeWidth={2} />
              </AreaChart>
            )}
          </ChartFrame>

          <div className="positions-table">
            <div className="positions-head">
              <span>Symbol</span>
              <span>Qty</span>
              <span>Last</span>
              <span>P&L</span>
            </div>
            {(snapshot?.portfolio.positions ?? []).map((position) => (
              <div className="positions-row" key={position.symbol}>
                <strong>{position.symbol}</strong>
                <span>{integer(position.quantity)}</span>
                <span>{currency(position.last_price)}</span>
                <span className={position.unrealized_pnl >= 0 ? 'positive' : 'negative'}>
                  {signedCurrency(position.unrealized_pnl)}
                </span>
              </div>
            ))}
          </div>
        </Panel>

        <aside className="side-rail">
          <Panel title="Order ticket" action={selectedSymbol}>
            <form className="ticket-form" onSubmit={submitOrder}>
              <div className="segmented-control">
                <button type="button" className={side === 'BUY' ? 'active buy' : ''} onClick={() => setSide('BUY')}>
                  Buy
                </button>
                <button type="button" className={side === 'SELL' ? 'active sell' : ''} onClick={() => setSide('SELL')}>
                  Sell
                </button>
              </div>

              <label>
                Type
                <select value={orderType} onChange={(event) => setOrderType(event.target.value as OrderType)}>
                  <option value="MARKET">Market</option>
                  <option value="LIMIT">Limit</option>
                </select>
              </label>

              <label>
                Quantity
                <input
                  min={1}
                  max={100000}
                  type="number"
                  value={quantity}
                  onChange={(event) => setQuantity(Number(event.target.value))}
                />
              </label>

              <label>
                Limit price
                <input
                  disabled={orderType === 'MARKET'}
                  min={0}
                  step="0.01"
                  type="number"
                  placeholder={selectedQuote ? String(side === 'BUY' ? selectedQuote.ask : selectedQuote.bid) : '0.00'}
                  value={limitPrice}
                  onChange={(event) => setLimitPrice(event.target.value)}
                />
              </label>

              <button className={`submit-order ${side.toLowerCase()}`} disabled={submitting || !snapshot} type="submit">
                <Send size={17} />
                {submitting ? 'Routing' : `${side} ${selectedSymbol}`}
              </button>
            </form>
            {orderResponse && (
              <div className={`order-result ${orderResponse.accepted ? 'accepted' : 'rejected'}`}>
                <strong>{orderResponse.accepted ? 'Accepted' : 'Rejected'}</strong>
                <span>
                  {orderResponse.fill
                    ? `${orderResponse.fill.quantity} @ ${currency(orderResponse.fill.price)}`
                    : orderResponse.reason}
                </span>
              </div>
            )}
          </Panel>

          <Panel title="Risk" action={snapshot ? `${snapshot.risk.concentration_percent}% conc.` : '--'}>
            <div className="risk-list">
              <RiskRow label="Buying power" value={snapshot ? currency(snapshot.risk.buying_power, 0) : '--'} />
              <RiskRow label="Gross exposure" value={snapshot ? currency(snapshot.risk.gross_exposure, 0) : '--'} />
              <RiskRow label="Sharpe" value={snapshot ? snapshot.risk.sharpe.toFixed(2) : '--'} />
              <RiskRow label="Max drawdown" value={snapshot ? percent(snapshot.risk.max_drawdown_percent, 2) : '--'} />
            </div>
          </Panel>
        </aside>
      </section>

      <section className="activity-grid">
        <Panel title="Recent fills" action={snapshot ? `${snapshot.recent_fills.length}` : '--'}>
          <ActivityList
            rows={(snapshot?.recent_fills ?? []).map((fill) => ({
              id: fill.id,
              left: `${fill.side} ${fill.quantity} ${fill.symbol}`,
              right: currency(fill.price),
              tone: fill.side === 'BUY' ? 'positive' : 'negative',
            }))}
          />
        </Panel>

        <Panel title="Open orders" action={snapshot ? `${snapshot.open_orders.length}` : '--'}>
          <ActivityList
            rows={(snapshot?.open_orders ?? []).map((order) => ({
              id: order.id,
              left: `${order.side} ${order.remaining_quantity} ${order.symbol}`,
              right: order.price ? currency(order.price) : 'MKT',
              tone: order.side === 'BUY' ? 'positive' : 'negative',
            }))}
            empty="No resting orders"
          />
        </Panel>

        <Panel title="Event log" action={snapshot ? compact(snapshot.market.event_log_offset) : '--'}>
          <ChartFrame className="event-chart">
            {({ width, height }) => (
              <LineChart width={width} height={height} data={snapshot?.pnl_series.slice(-36) ?? []}>
                <CartesianGrid stroke="#2d2d2d" vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis hide />
                <Tooltip contentStyle={tooltipStyle} formatter={(value) => currency(Number(value))} />
                <Line type="monotone" dataKey="pnl" dot={false} stroke="#f1b85b" strokeWidth={2} />
              </LineChart>
            )}
          </ChartFrame>
        </Panel>
      </section>
    </main>
  )
}

function Metric({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode
  label: string
  value: string
  tone?: 'positive' | 'negative'
}) {
  return (
    <article className="metric-card">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </article>
  )
}

function Panel({
  title,
  action,
  children,
  className = '',
}: {
  title: string
  action?: string
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-header">
        <h2>{title}</h2>
        {action && <span>{action}</span>}
      </div>
      {children}
    </section>
  )
}

function RiskRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="risk-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function ActivityList({
  rows,
  empty = 'Waiting for activity',
}: {
  rows: Array<{ id: string; left: string; right: string; tone?: 'positive' | 'negative' }>
  empty?: string
}) {
  if (!rows.length) {
    return <p className="empty-state">{empty}</p>
  }

  return (
    <div className="activity-list">
      {rows.map((row) => (
        <div className="activity-row" key={row.id}>
          <span className={row.tone}>{row.left}</span>
          <strong>{row.right}</strong>
        </div>
      ))}
    </div>
  )
}

function ChartFrame({
  children,
  className,
}: {
  children: (size: { width: number; height: number }) => ReactNode
  className: string
}) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })

  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return

    const updateSize = () => {
      setSize({
        width: Math.max(1, element.clientWidth),
        height: Math.max(1, element.clientHeight),
      })
    }

    updateSize()
    const observer = new ResizeObserver(updateSize)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return (
    <div className={className} ref={ref}>
      {size.width > 1 && size.height > 1 ? children(size) : null}
    </div>
  )
}

const tooltipStyle = {
  background: '#191919',
  border: '1px solid #333',
  borderRadius: 6,
  color: '#f4f4f4',
}

const seedQuotes: SymbolQuote[] = [
  { symbol: 'AAPL', name: 'Apple', price: 203.18, change_percent: 1.21, volume: 0, bid: 203.12, ask: 203.24 },
  { symbol: 'AMZN', name: 'Amazon', price: 183.42, change_percent: 0.86, volume: 0, bid: 183.36, ask: 183.48 },
  { symbol: 'NFLX', name: 'Netflix', price: 656.28, change_percent: 1.26, volume: 0, bid: 656.11, ask: 656.44 },
  { symbol: 'TSLA', name: 'Tesla', price: 249.87, change_percent: -2.09, volume: 0, bid: 249.79, ask: 249.95 },
]

export default App
