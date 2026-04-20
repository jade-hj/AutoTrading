import { useState, useCallback, useRef, useEffect } from 'react'
import { logsApi, Trade, LogEntry } from '../api/client'
import { usePolling } from '../hooks/usePolling'
import { useWebSocket } from '../hooks/useWebSocket'

function fmt(n: number) { return n.toLocaleString('ko-KR') }

export default function Logs() {
  const [tab,     setTab]    = useState<'trades' | 'system'>('trades')
  const [trades,  setTrades] = useState<Trade[]>([])
  const [logs,    setLogs]   = useState<LogEntry[]>([])
  const logEndRef = useRef<HTMLDivElement>(null)

  const fetchTrades = useCallback(async () => {
    try {
      const res = await logsApi.trades()
      setTrades(res.data.trades)
    } catch { /* ignore */ }
  }, [])

  const fetchLogs = useCallback(async () => {
    try {
      const res = await logsApi.system(200)
      setLogs(res.data.logs)
    } catch { /* ignore */ }
  }, [])

  usePolling(fetchTrades, 10_000)
  usePolling(fetchLogs,   10_000, tab === 'system')

  // WebSocket 으로 실시간 로그 수신
  useWebSocket((msg) => {
    if (msg.type === 'log') {
      setLogs((prev) => {
        const next = [...prev, msg.data as LogEntry]
        return next.slice(-500)
      })
    }
    if (msg.type === 'trade') {
      setTrades((prev) => [msg.data as Trade, ...prev])
    }
  })

  // 시스템 로그 자동 스크롤
  useEffect(() => {
    if (tab === 'system') logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs, tab])

  const levelColor: Record<string, string> = {
    INFO:    'text-[#8b949e]',
    WARNING: 'text-[#e3b341]',
    ERROR:   'text-[#f85149]',
    DEBUG:   'text-[#30363d]',
  }

  return (
    <div className="p-5 flex flex-col h-full gap-4">
      <div className="flex items-center gap-4">
        <h2 className="text-sm font-semibold text-white">로그</h2>
        <div className="flex gap-1">
          {(['trades', 'system'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`text-xs px-3 py-1 rounded transition-colors
                ${tab === t ? 'bg-[#30363d] text-white' : 'text-[#8b949e] hover:text-white'}`}>
              {t === 'trades' ? '거래 기록' : '시스템 로그'}
            </button>
          ))}
        </div>
      </div>

      {tab === 'trades' && (
        <div className="flex-1 overflow-y-auto">
          <div className="bg-[#161b22] border border-[#30363d] rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[#30363d]">
                  {['시간','구분','종목','가격','수량','실현 손익','사유'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left text-[#8b949e] font-normal">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center text-[#8b949e]">당일 거래 내역 없음</td>
                  </tr>
                ) : trades.map((t, i) => (
                  <tr key={i} className="border-b border-[#21262d] hover:bg-[#21262d] transition-colors">
                    <td className="px-3 py-2 text-[#8b949e]">{t.timestamp}</td>
                    <td className="px-3 py-2">
                      <span className={`font-bold ${t.action === 'BUY' ? 'text-[#3fb950]' : 'text-[#f85149]'}`}>
                        {t.action === 'BUY' ? '매수' : '매도'}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <p className="text-white">{t.stock_name}</p>
                      <p className="text-[#8b949e]">{t.stock_code}</p>
                    </td>
                    <td className="px-3 py-2 text-white">{fmt(t.price)}원</td>
                    <td className="px-3 py-2 text-white">{t.quantity}주</td>
                    <td className="px-3 py-2">
                      {t.action === 'SELL' ? (
                        <span className={`font-medium ${t.pnl >= 0 ? 'text-[#3fb950]' : 'text-[#f85149]'}`}>
                          {t.pnl >= 0 ? '+' : ''}{fmt(Math.round(t.pnl))}원
                          <span className="text-[#8b949e] ml-1">({t.pnl_rate >= 0 ? '+' : ''}{t.pnl_rate.toFixed(2)}%)</span>
                        </span>
                      ) : '-'}
                    </td>
                    <td className="px-3 py-2 text-[#8b949e] max-w-xs truncate">{t.reason || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'system' && (
        <div className="flex-1 bg-[#0d1117] border border-[#30363d] rounded-lg p-3 overflow-y-auto font-mono text-xs">
          {logs.map((log, i) => (
            <div key={i} className="flex gap-2 leading-5">
              <span className="text-[#30363d] shrink-0">{log.ts}</span>
              <span className={`shrink-0 w-14 ${levelColor[log.level] ?? 'text-[#8b949e]'}`}>{log.level}</span>
              <span className="text-[#58a6ff] shrink-0 w-24 truncate">{log.name}</span>
              <span className="text-[#c9d1d9]">{log.message}</span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}
    </div>
  )
}
