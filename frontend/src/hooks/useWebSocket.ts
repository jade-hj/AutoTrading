import { useEffect, useRef, useCallback } from 'react'

type WsMessage = { type: string; data: unknown }

export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  const wsRef     = useRef<WebSocket | null>(null)
  const timerRef  = useRef<ReturnType<typeof setInterval> | null>(null)
  const retryRef  = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/updates`)
    wsRef.current = ws

    ws.onopen = () => {
      // 30초마다 ping 전송 (연결 유지)
      timerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping')
      }, 30_000)
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as WsMessage
        if (msg.type !== 'pong') onMessage(msg)
      } catch { /* ignore */ }
    }

    ws.onclose = () => {
      if (timerRef.current) clearInterval(timerRef.current)
      // 3초 후 재연결
      retryRef.current = setTimeout(connect, 3_000)
    }

    ws.onerror = () => ws.close()
  }, [onMessage])

  useEffect(() => {
    connect()
    return () => {
      if (timerRef.current)  clearInterval(timerRef.current)
      if (retryRef.current)  clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, [connect])
}
