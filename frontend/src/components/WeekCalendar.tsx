import type { CalendarSlot } from '../types'
import { addDays, toISODate, formatTime } from '../utils'

interface Props {
  weekStart: Date
  slots: CalendarSlot[]
  onPrev: () => void
  onNext: () => void
  onToday: () => void
}

// Clinic hours: 09:00–17:00 in 30-min blocks (matches the seeded slots)
const ROW_TIMES = Array.from({ length: 16 }, (_, i) => {
  const minutes = 9 * 60 + i * 30
  const h = String(Math.floor(minutes / 60)).padStart(2, '0')
  const m = String(minutes % 60).padStart(2, '0')
  return `${h}:${m}:00`
})

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

export default function WeekCalendar({ weekStart, slots, onPrev, onNext, onToday }: Props) {
  const days = DAY_LABELS.map((label, i) => {
    const d = addDays(weekStart, i)
    return { label, date: d, iso: toISODate(d) }
  })

  const byKey = new Map<string, CalendarSlot>()
  for (const s of slots) byKey.set(`${s.date}_${s.start_time}`, s)

  const todayIso = toISODate(new Date())
  const rangeLabel = `${days[0].iso.split('-').reverse().join('/')} – ${days[4].iso
    .split('-')
    .reverse()
    .join('/')}`

  return (
    <div className="bg-white rounded-card shadow-card p-6">
      <div className="flex items-center justify-between mb-5">
        <h2 className="font-inter font-medium text-ink text-xl">Appointments</h2>
        <div className="flex items-center gap-2">
          <span className="font-manrope text-warm-500 text-sm mr-2">{rangeLabel}</span>
          <button
            onClick={onPrev}
            className="w-8 h-8 rounded-btn border border-border-gray text-warm-600 hover:bg-cream transition-colors"
            aria-label="Previous week"
          >
            ‹
          </button>
          <button
            onClick={onToday}
            className="px-3 h-8 rounded-btn border border-border-gray font-manrope font-medium text-sm text-ink hover:bg-cream transition-colors"
          >
            Today
          </button>
          <button
            onClick={onNext}
            className="w-8 h-8 rounded-btn border border-border-gray text-warm-600 hover:bg-cream transition-colors"
            aria-label="Next week"
          >
            ›
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <div className="grid grid-cols-[64px_repeat(5,minmax(120px,1fr))] min-w-[680px]">
          {/* Header row */}
          <div />
          {days.map(d => (
            <div
              key={d.iso}
              className={`pb-2 text-center border-b border-border-gray ${
                d.iso === todayIso ? 'text-prosper-orange' : 'text-warm-600'
              }`}
            >
              <div className="font-manrope font-bold text-sm">{d.label}</div>
              <div className="font-manrope text-xs text-warm-500">
                {d.iso.split('-').slice(1).reverse().join('/')}
              </div>
            </div>
          ))}

          {/* Time rows */}
          {ROW_TIMES.map(t => (
            <Row key={t} time={t} days={days} byKey={byKey} />
          ))}
        </div>
      </div>

      <Legend />
    </div>
  )
}

function Row({
  time,
  days,
  byKey,
}: {
  time: string
  days: { iso: string }[]
  byKey: Map<string, CalendarSlot>
}) {
  return (
    <>
      <div className="h-12 pr-2 -mt-2 text-right font-manrope text-xs text-warm-500">
        {formatTime(time)}
      </div>
      {days.map(d => {
        const slot = byKey.get(`${d.iso}_${time}`)
        return <Cell key={`${d.iso}_${time}`} slot={slot} />
      })}
    </>
  )
}

function Cell({ slot }: { slot?: CalendarSlot }) {
  if (!slot) {
    // No slot exists for this block (outside clinic hours / not seeded)
    return <div className="h-12 border-b border-r border-border-gray bg-cream/40" />
  }
  if (slot.is_booked) {
    return (
      <div className="h-12 border-b border-r border-border-gray p-0.5">
        <div className="h-full rounded-md bg-prosper-orange/10 border-l-2 border-prosper-orange px-1.5 py-0.5 overflow-hidden">
          <p className="font-manrope font-medium text-[11px] leading-tight text-prosper-orange truncate">
            {slot.patient_name ?? 'Booked'}
          </p>
        </div>
      </div>
    )
  }
  return <div className="h-12 border-b border-r border-border-gray bg-white" />
}

function Legend() {
  return (
    <div className="flex items-center gap-5 mt-4 font-manrope text-xs text-warm-500">
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded-sm bg-white border border-border-gray" /> Available
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded-sm bg-prosper-orange/10 border-l-2 border-prosper-orange" /> Booked
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded-sm bg-cream/40 border border-border-gray" /> Unavailable
      </span>
    </div>
  )
}
