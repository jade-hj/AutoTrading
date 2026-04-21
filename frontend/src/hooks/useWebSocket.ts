import { useEffect, useRef } from 'react'

type WsMessage = { type: string; data: unknown }

export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  // onMessage 를 ref 로 보관 → 콜백이 바뀌어도 WebSocket 재연결 없음
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const wsRef    = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let destroyed = false

    function connect() {
      if (destroyed) return
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${protocol}://${window.location.host}/ws/updates`)
      wsRef.current = ws

      ws.onopen = () => {
        // 30초마다 ping (연결 유지)
        timerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping')
        }, 30_000)
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data) as WsMessage
          if (msg.type !== 'pong') onMessageRef.current(msg)
        } catch { /* ignore */ }
      }

      ws.onclose = () => {
        if (timerRef.current) clearInterval(timerRef.current)
        if (!destroyed) retryRef.current = setTimeout(connect, 3_000)
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      destroyed = true
      if (timerRef.current) clearInterval(timerRef.current)
      if (retryRef.current) clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, []) // 마운트 시 1회만 실행
}
