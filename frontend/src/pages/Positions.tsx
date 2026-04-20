import { useState, useCallback } from 'react'
import { positionsApi, Position } from '../api/client'
import { usePolling } from '../hooks/usePolling'

function fmt(n: number) { return n.toLocaleString('ko-KR') }

export default function Positions() {
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading]     = useState(true)
  const [closing, setClosing]     = useState<string | null>(null)

  const fetchPositions = useCallback(async () => {
    try {
      const res = await positionsApi.list()
      setPositions(res.data)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }, [])

  usePolling(fetchPositions, 5_000)

  const handleClose = async (code: string) => {
    if (!confirm(`${code} 포지션을 시장가로 청산하시겠습니까?`)) return
    setClosing(code)
    try {
      await positionsApi.close(code)
      await fetchPositions()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '청산 실패'
      alert(msg)
    } finally {
      setClosing(null)
    }
  }

  if (loading) {
    return (
      <div className="p-5">
        <div className="h-32 bg-[#161b22] rounded-lg animate-pulse" />
      </div>
    )
  }

  return (
    <div className="p-5 space-y-4 overflow-y-auto h-full">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">
          보유 포지션 <span className="text-[#8b949e] font-normal ml-1">{positions.length}종목</span>
        </h2>
        <button onClick={fetchPositions}
          className="text-xs text-[#58a6ff] hover:text-white transition-colors">
          새로고침
        </button>
      </div>

      {positions.length === 0 ? (
        <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-8 text-center text-[#8b949e] text-xs">
          보유 중인 포지션이 없습니다
        </div>
      ) : (
        <div className="space-y-2">
          {positions.map((pos) => (
            <div key={pos.stock_code}
              className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <span className="text-white font-medium text-sm">{pos.stock_name}</span>
                  <span className="text-[#8b949e] text-xs ml-2">{pos.stock_code}</span>
                  <span className="text-[#8b949e] text-xs ml-2">{pos.quantity}주</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className="text-white font-medium text-sm">{fmt(pos.current_price)}원</p>
                    <p className={`text-xs font-medium ${pos.pnl_rate >= 0 ? 'text-[#3fb950]' : 'text-[#f85149]'}`}>
                      {pos.pnl_rate >= 0 ? '+' : ''}{pos.pnl_rate.toFixed(2)}%
                      &nbsp;({pos.pnl >= 0 ? '+' : ''}{fmt(Math.round(pos.pnl))}원)
                    </p>
                  </div>
                  <button
                    onClick={() => handleClose(pos.stock_code)}
                    disabled={closing === pos.stock_code}
                    className="text-xs px-3 py-1 rounded border border-[#f85149]/40 text-[#f85149]
                               hover:bg-[#f85149]/10 disabled:opacity-50 transition-colors">
                    {closing === pos.stock_code ? '청산 중...' : '청산'}
                  </button>
                </div>
              </div>

              {/* 가격 레벨 바 */}
              <div className="grid grid-cols-4 gap-2 text-xs">
                <div className="bg-[#21262d] rounded p-2">
                  <p className="text-[#8b949e] mb-0.5">진입가</p>
                  <p className="text-white">{fmt(pos.entry_price)}</p>
                </div>
                <div className="bg-[#f85149]/10 border border-[#f85149]/20 rounded p-2">
                  <p className="text-[#f85149] mb-0.5">손절</p>
                  <p className="text-white">{fmt(pos.stop_loss)}</p>
                </div>
                <div className={`rounded p-2 ${pos.tp1_hit ? 'bg-[#3fb950]/20 border border-[#3fb950]/40' : 'bg-[#21262d]'}`}>
                  <p className="text-[#3fb950] mb-0.5">1차 익절{pos.tp1_hit ? ' ✓' : ''}</p>
                  <p className="text-white">{fmt(pos.tp1)}</p>
                </div>
                <div className="bg-[#21262d] rounded p-2">
                  <p className="text-[#3fb950] mb-0.5">2차 익절</p>
                  <p className="text-white">{fmt(pos.tp2)}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
