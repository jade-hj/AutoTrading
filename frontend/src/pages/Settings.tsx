import { useState, useCallback } from 'react'
import { systemApi, SystemSettings } from '../api/client'
import { usePolling } from '../hooks/usePolling'

type Section = 'common' | 'am' | 'pm' | 'scan'

const labels: Record<string, Record<string, string>> = {
  scan: {
    scan_top_n:      '후보 종목 수',
    scan_min_price:  '최소 주가 (원)',
    scan_min_volume: '최소 거래량',
  },
  common: {
    interval_sec:     '스캔 주기 (초)',
    monitor_sec:      '모니터 주기 (초)',
    max_positions:    '최대 동시 보유',
    stop_loss:        '손절 비율',
    take_profit_1:    '1차 익절',
    take_profit_2:    '2차 익절',
    daily_loss_limit: '일일 손실 한도',
    kospi_range:      '코스피 관망 범위',
    exec_start:       '거래 시작',
    exec_end:         '거래 종료',
  },
  am: {
    end:             '오전 종료',
    volume_surge:    '거래량 배수 기준',
    rsi_min:         'RSI 하한',
    rsi_max:         'RSI 상한',
    change_rate_max: '등락률 상한 (%)',
    gap_limit:       '갭 필터',
  },
  pm: {
    start:           '오후 시작',
    volume_surge:    '거래량 배수 기준',
    rsi_min:         'RSI 하한',
    rsi_max:         'RSI 상한',
    change_rate_min: '등락률 하한 (%)',
    change_rate_max: '등락률 상한 (%)',
    gap_limit:       '갭 필터',
  },
}

const keyMap: Record<Section, Record<string, string>> = {
  scan: {
    scan_top_n:      'SCAN_TOP_N',
    scan_min_price:  'SCAN_MIN_PRICE',
    scan_min_volume: 'SCAN_MIN_VOLUME',
  },
  common: {
    stop_loss:        'SCALPING_STOP_LOSS',
    take_profit_1:    'SCALPING_TAKE_PROFIT_1',
    take_profit_2:    'SCALPING_TAKE_PROFIT_2',
    max_positions:    'SCALPING_MAX_POSITIONS',
    daily_loss_limit: 'SCALPING_DAILY_LOSS_LIMIT',
  },
  am: {
    volume_surge:    'SCALPING_AM_VOLUME_SURGE',
    rsi_min:         'SCALPING_AM_RSI_MIN',
    rsi_max:         'SCALPING_AM_RSI_MAX',
    change_rate_max: 'SCALPING_AM_CHANGE_RATE_MAX',
    gap_limit:       'SCALPING_AM_GAP_LIMIT',
  },
  pm: {
    volume_surge:    'SCALPING_PM_VOLUME_SURGE',
    rsi_min:         'SCALPING_PM_RSI_MIN',
    rsi_max:         'SCALPING_PM_RSI_MAX',
    change_rate_min: 'SCALPING_PM_CHANGE_RATE_MIN',
    change_rate_max: 'SCALPING_PM_CHANGE_RATE_MAX',
    gap_limit:       'SCALPING_PM_GAP_LIMIT',
  },
}

export default function Settings() {
  const [settings, setSettings] = useState<SystemSettings | null>(null)
  const [saving, setSaving]     = useState<string | null>(null)
  const [saved,  setSaved]      = useState<string | null>(null)
  const [activeSection, setSection] = useState<Section>('am')

  const fetchSettings = useCallback(async () => {
    try {
      const res = await systemApi.getSettings()
      setSettings(res.data)
    } catch { /* ignore */ }
  }, [])

  usePolling(fetchSettings, 30_000)

  const handleSave = async (section: Section, key: string, value: string) => {
    const settingKey = keyMap[section]?.[key]
    if (!settingKey) return
    setSaving(`${section}.${key}`)
    try {
      await systemApi.patchSetting(settingKey, parseFloat(value) || value)
      setSaved(`${section}.${key}`)
      setTimeout(() => setSaved(null), 2000)
      await fetchSettings()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '저장 실패'
      alert(msg)
    } finally {
      setSaving(null)
    }
  }

  const sections: { id: Section; label: string }[] = [
    { id: 'am',     label: '오전 모드' },
    { id: 'pm',     label: '오후 모드' },
    { id: 'common', label: '공통 설정' },
    { id: 'scan',   label: '스캔 설정' },
  ]

  const currentData = settings?.[activeSection] as Record<string, unknown> | undefined

  return (
    <div className="p-5 space-y-4 overflow-y-auto h-full">
      <h2 className="text-sm font-semibold text-white">설정</h2>
      <p className="text-[#8b949e] text-xs">봇 실행 중에도 설정 변경이 가능합니다. 다음 스캔 주기부터 적용됩니다.</p>

      {/* 섹션 탭 */}
      <div className="flex gap-1">
        {sections.map((s) => (
          <button key={s.id} onClick={() => setSection(s.id)}
            className={`text-xs px-3 py-1.5 rounded transition-colors
              ${activeSection === s.id ? 'bg-[#58a6ff]/20 text-[#58a6ff] border border-[#58a6ff]/40' : 'text-[#8b949e] hover:text-white'}`}>
            {s.label}
          </button>
        ))}
      </div>

      {/* 설정 항목 */}
      <div className="bg-[#161b22] border border-[#30363d] rounded-lg divide-y divide-[#21262d]">
        {currentData ? Object.entries(currentData).map(([key, value]) => {
          const label      = labels[activeSection]?.[key] ?? key
          const settingKey = keyMap[activeSection]?.[key]
          const fieldId    = `${activeSection}.${key}`
          const isSaving   = saving === fieldId
          const wasSaved   = saved  === fieldId

          return (
            <div key={key} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-white text-xs">{label}</p>
                <p className="text-[#8b949e] text-xs">{settingKey ?? key}</p>
              </div>
              <div className="flex items-center gap-2">
                {settingKey ? (
                  <>
                    <input
                      type="text"
                      defaultValue={String(value)}
                      onBlur={(e) => handleSave(activeSection, key, e.target.value)}
                      className="w-24 bg-[#21262d] border border-[#30363d] rounded px-2 py-1 text-xs text-white
                                 text-right focus:outline-none focus:border-[#58a6ff]"
                    />
                    {isSaving && <span className="text-[#8b949e] text-xs">저장 중...</span>}
                    {wasSaved && <span className="text-[#3fb950] text-xs">✓</span>}
                  </>
                ) : (
                  <span className="text-[#8b949e] text-xs">{String(value)}</span>
                )}
              </div>
            </div>
          )
        }) : (
          <div className="px-4 py-8 text-center text-[#8b949e] text-xs">로딩 중...</div>
        )}
      </div>
    </div>
  )
}
