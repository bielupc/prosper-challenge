import { Fragment } from 'react'
import type { CalendarSlot } from '../types'
import { addDays, toISODate, formatTime } from '../utils'

interface Props {
  weekStart: Date
  slots: CalendarSlot[]
  onPrev: () => void
  onNext: () => void
  onToday: () => void
}

const ROW_TIMES = Array.from({ length: 16 }, (_, i) => {
  const minutes = 9 * 60 + i * 30
  const h = String(Math.floor(minutes / 60)).padStart(2, '0')
  const m = String(minutes % 60).padStart(2, '0')
  return `${h}:${m}:00`
})

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

// One rendered cell per day column. Consecutive booked slots for the same patient
// collapse into a single 'booked' cell that spans `span` rows; the slots it covers
// become 'covered' and are not rendered.
type DayCell =
  | { kind: 'empty'; ti: number }
  | { kind: 'available'; ti: number }
  | { kind: 'covered'; ti: number }
  | { kind: 'booked'; ti: number; span: number; name: string; start: string; end: string }

function buildDay(iso: string, byKey: Map<string, CalendarSlot>): DayCell[] {
  const cells: DayCell[] = []
  let ti = 0
  while (ti < ROW_TIMES.length) {
    const slot = byKey.get(`${iso}_${ROW_TIMES[ti]}`)
    if (!slot) {
      cells.push({ kind: 'empty', ti })
      ti++
      continue
    }
    if (!slot.is_booked) {
      cells.push({ kind: 'available', ti })
      ti++
      continue
    }
    // Booked. Merge forward while the next contiguous slot belongs to the same appointment.
    const apptId = slot.appointment_id
    const name = slot.patient_name
    let span = 1
    if (apptId) {
      while (ti + span < ROW_TIMES.length) {
        const next = byKey.get(`${iso}_${ROW_TIMES[ti + span]}`)
        if (next && next.is_booked && next.appointment_id === apptId) span++
        else break
      }
    }
    const last = byKey.get(`${iso}_${ROW_TIMES[ti + span - 1]}`)!
    cells.push({
      kind: 'booked',
      ti,
      span,
      name: name ?? 'Booked',
      start: ROW_TIMES[ti],
      end: last.end_time,
    })
    for (let k = 1; k < span; k++) cells.push({ kind: 'covered', ti: ti + k })
    ti += span
  }
  return cells
}

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
        <div
          className="grid grid-cols-[64px_repeat(5,minmax(120px,1fr))] min-w-[680px]"
          style={{ gridTemplateRows: `auto repeat(${ROW_TIMES.length}, 3rem)` }}
        >
          {/* Header corner */}
          <div style={{ gridColumn: 1, gridRow: 1 }} />
          {days.map((d, di) => (
            <div
              key={d.iso}
              style={{ gridColumn: di + 2, gridRow: 1 }}
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

          {/* Time labels */}
          {ROW_TIMES.map((t, ti) => (
            <div
              key={t}
              style={{ gridColumn: 1, gridRow: ti + 2 }}
              className="pr-2 -mt-2 text-right font-manrope text-xs text-warm-500"
            >
              {formatTime(t)}
            </div>
          ))}

          {/* Day cells */}
          {days.map((d, di) => (
            <Fragment key={d.iso}>
              {buildDay(d.iso, byKey).map(cell => (
                <DayCellView key={cell.ti} cell={cell} col={di + 2} />
              ))}
            </Fragment>
          ))}
        </div>
      </div>

      <Legend />
    </div>
  )
}

function DayCellView({ cell, col }: { cell: DayCell; col: number }) {
  if (cell.kind === 'covered') return null

  const gridRow = cell.kind === 'booked' ? `${cell.ti + 2} / span ${cell.span}` : cell.ti + 2
  const style = { gridColumn: col, gridRow }

  if (cell.kind === 'empty') {
    // No slot exists for this block (outside clinic hours / not seeded)
    return <div style={style} className="border-b border-r border-border-gray bg-cream/40" />
  }
  if (cell.kind === 'available') {
    return <div style={style} className="border-b border-r border-border-gray bg-white" />
  }
  return (
    <div style={style} className="border-b border-r border-border-gray p-0.5">
      <div className="h-full rounded-md bg-prosper-orange/10 border-l-2 border-prosper-orange px-1.5 py-1 overflow-hidden">
        <p className="font-manrope font-medium text-[11px] leading-tight text-prosper-orange truncate">
          {cell.name}
        </p>
        <p className="font-manrope text-[10px] leading-tight text-prosper-orange/70">
          {formatTime(cell.start)}–{formatTime(cell.end)}
        </p>
      </div>
    </div>
  )
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
