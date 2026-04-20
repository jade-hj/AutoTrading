import { SystemStatus } from '../api/client'

interface HeaderProps {
  status:    SystemStatus | null
  onStart:   () => void
  onStop:    () => void
  loading:   boolean
}

function fmt(sec: number | null): string {
  if (sec === null) return '-'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m ${s}s`
}

export default function Header({ status, onStart, onStop, loading }: HeaderProps) {
  const running = status?.is_running ?? false

  return (
    <header className="h-14 bg-[#161b22] border-b border-[#30363d] flex items-center px-5 gap-4 shrink-0">
      {/* 로고 */}
      <span className="text-[#58a6ff] font-bold text-base tracking-wide mr-2">
        AutoTrading
      </span>

      {/* 봇 상태 뱃지 */}
      <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border
        ${running
          ? 'border-[#3fb950] text-[#3fb950] bg-[#3fb950]/10'
          : 'border-[#30363d]  text-[#8b949e] bg-[#21262d]'}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${running ? 'bg-[#3fb950] animate-pulse' : 'bg-[#8b949e]'}`} />
        {running ? '실행 중' : '중지됨'}
      </div>

      {/* 세션 / 모드 */}
      {status && (
        <>
          <span className="text-[#8b949e] text-xs">
            {status.mode} · {status.session !== '-' ? (status.session === 'AM' ? '오전' : '오후') : '-'} 세션
          </span>
          {running && (
            <span className="text-[#8b949e] text-xs">
              가동 {fmt(status.uptime_sec)}
            </span>
          )}
        </>
      )}

      <div className="ml-auto flex gap-2">
        {running ? (
          <button
            onClick={onStop}
            disabled={loading}
            className="px-4 py-1.5 text-xs rounded bg-[#f85149]/20 text-[#f85149] border border-[#f85149]/40
                       hover:bg-[#f85149]/30 disabled:opacity-50 transition-colors"
          >
            중지
          </button>
        ) : (
          <button
            onClick={onStart}
            disabled={loading}
            className="px-4 py-1.5 text-xs rounded bg-[#3fb950]/20 text-[#3fb950] border border-[#3fb950]/40
                       hover:bg-[#3fb950]/30 disabled:opacity-50 transition-colors"
          >
            시작
          </button>
        )}
      </div>
    </header>
  )
}
