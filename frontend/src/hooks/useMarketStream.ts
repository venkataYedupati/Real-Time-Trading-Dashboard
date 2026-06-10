import { useEffect, useRef, useState } from 'react'
import type { MarketSnapshot } from '../types'

type ConnectionState = 'connecting' | 'connected' | 'disconnected'

function marketSocketUrl(symbol: string) {
  const explicit = import.meta.env.VITE_WS_URL as string | undefined
  if (explicit) {
    const separator = explicit.includes('?') ? '&' : '?'
    return `${explicit}${separator}symbol=${symbol}`
  }

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}/ws/market?symbol=${symbol}`
}

export function useMarketStream(symbol: string) {
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null)
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting')
  const reconnectTimer = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    let socket: WebSocket | null = null

    const connect = () => {
      setConnectionState('connecting')
      socket = new WebSocket(marketSocketUrl(symbol))

      socket.onopen = () => {
        if (!cancelled) {
          setConnectionState('connected')
        }
      }

      socket.onmessage = (event) => {
        if (!cancelled) {
          setSnapshot(JSON.parse(event.data) as MarketSnapshot)
        }
      }

      socket.onclose = () => {
        if (cancelled) return
        setConnectionState('disconnected')
        reconnectTimer.current = window.setTimeout(connect, 1200)
      }

      socket.onerror = () => {
        socket?.close()
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer.current) {
        window.clearTimeout(reconnectTimer.current)
      }
      socket?.close()
    }
  }, [symbol])

  return { snapshot, connectionState }
}
