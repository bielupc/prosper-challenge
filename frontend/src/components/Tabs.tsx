interface TabItem {
  id: string
  label: string
  count?: number
}

interface Props {
  tabs: TabItem[]
  active: string
  onChange: (id: string) => void
}

export default function Tabs({ tabs, active, onChange }: Props) {
  return (
    <div className="flex gap-6 border-b border-border-gray mb-6">
      {tabs.map(t => {
        const isActive = t.id === active
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className={`relative pb-3 font-manrope font-bold text-sm transition-colors ${
              isActive ? 'text-ink' : 'text-warm-500 hover:text-warm-700'
            }`}
          >
            {t.label}
            {t.count !== undefined && (
              <span className="ml-1.5 font-medium text-warm-500">{t.count}</span>
            )}
            {isActive && (
              <span className="absolute left-0 -bottom-px h-0.5 w-full bg-prosper-orange rounded-full" />
            )}
          </button>
        )
      })}
    </div>
  )
}
