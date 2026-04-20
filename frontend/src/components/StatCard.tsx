interface StatCardProps {
  label:    string
  value:    string | number
  sub?:     string
  color?:   'green' | 'red' | 'blue' | 'yellow' | 'default'
  loading?: boolean
}

const colorMap = {
  green:   'text-[#3fb950]',
  red:     'text-[#f85149]',
  blue:    'text-[#58a6ff]',
  yellow:  'text-[#e3b341]',
  default: 'text-white',
}

export default function StatCard({ label, value, sub, color = 'default', loading }: StatCardProps) {
  return (
    <div className="bg-[#161b22] border border-[#30363d] rounded-lg p-4">
      <p className="text-[#8b949e] text-xs mb-1">{label}</p>
      {loading ? (
        <div className="h-7 bg-[#21262d] rounded animate-pulse w-24" />
      ) : (
        <p className={`text-xl font-bold ${colorMap[color]}`}>{value}</p>
      )}
      {sub && <p className="text-[#8b949e] text-xs mt-1">{sub}</p>}
    </div>
  )
}
