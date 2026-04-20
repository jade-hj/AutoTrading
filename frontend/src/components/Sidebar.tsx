type Page = 'dashboard' | 'positions' | 'scan' | 'chart' | 'logs' | 'settings'

interface SidebarProps {
  current:  Page
  onChange: (p: Page) => void
}

const items: { id: Page; label: string; icon: string }[] = [
  { id: 'dashboard', label: '대시보드',   icon: '▣' },
  { id: 'positions', label: '포지션',     icon: '◈' },
  { id: 'scan',      label: '종목 스캔',  icon: '⊙' },
  { id: 'chart',     label: '차트',       icon: '◫' },
  { id: 'logs',      label: '거래 로그',  icon: '≡' },
  { id: 'settings',  label: '설정',       icon: '⚙' },
]

export default function Sidebar({ current, onChange }: SidebarProps) {
  return (
    <nav className="w-40 bg-[#161b22] border-r border-[#30363d] flex flex-col shrink-0 py-3">
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => onChange(item.id)}
          className={`flex items-center gap-2.5 px-4 py-2.5 text-xs transition-colors text-left
            ${current === item.id
              ? 'text-white bg-[#21262d] border-r-2 border-[#58a6ff]'
              : 'text-[#8b949e] hover:text-white hover:bg-[#21262d]'}`}
        >
          <span>{item.icon}</span>
          {item.label}
        </button>
      ))}
    </nav>
  )
}

export type { Page }
