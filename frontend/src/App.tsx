import { useCallback, useEffect, useState } from 'react'
import Header from './components/Header'
import StatsBar from './components/StatsBar'
import PatientsTable from './components/PatientsTable'
import WeekCalendar from './components/WeekCalendar'
import AuditLog from './components/AuditLog'
import SimulationTab from './components/SimulationTab'
import Tabs from './components/Tabs'
import type { DashboardData, CalendarSlot } from './types'
import { mondayOf, toISODate, addDays } from './utils'
import { API_URL, headers } from './api'


type Tab = 'appointments' | 'patients' | 'audit' | 'simulation'

function initialWeek(): Date {
  const today = new Date()
  const dow = today.getDay() // 0 = Sun, 6 = Sat
  return dow === 0 || dow === 6 ? mondayOf(addDays(today, 7)) : mondayOf(today)
}

export default function App() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [slots, setSlots] = useState<CalendarSlot[]>([])
  const [weekStart, setWeekStart] = useState(initialWeek)
  const [tab, setTab] = useState<Tab>('appointments')

  const fetchDashboard = useCallback(() => {
    fetch(`${API_URL}/dashboard`, { headers })
      .then(r => r.json())
      .then(setData)
      .catch(console.error)
  }, [])

  const fetchCalendar = useCallback(() => {
    fetch(`${API_URL}/calendar?start=${toISODate(weekStart)}`, { headers })
      .then(r => r.json())
      .then(setSlots)
      .catch(console.error)
  }, [weekStart])

  // Initial load
  useEffect(() => {
    fetchDashboard()
    fetchCalendar()
  }, [fetchDashboard, fetchCalendar])

  // Real-time updates via SSE stream (fetch keeps X-API-Key in the header)
  useEffect(() => {
    let active = true

    const connect = () => {
      if (!active) return
      fetch(`${API_URL}/events`, { headers })
        .then(async res => {
          const reader = res.body!.getReader()
          const decoder = new TextDecoder()
          while (active) {
            const { done, value } = await reader.read()
            if (done) break
            if (decoder.decode(value).includes('data:')) {
              fetchDashboard()
              fetchCalendar()
            }
          }
        })
        .catch(() => {})
        .finally(() => { if (active) setTimeout(connect, 2000) })
    }

    connect()
    return () => { active = false }
  }, [fetchDashboard, fetchCalendar])

  return (
    <div className="min-h-screen bg-cream">
      <Header />
      <main className="max-w-[1200px] mx-auto px-8 py-10 space-y-8">
        <StatsBar data={data} />

        <div>
          <Tabs
            tabs={[
              { id: 'appointments', label: 'Appointments' },
              { id: 'patients', label: 'Patients', count: data?.total_patients },
              { id: 'audit', label: 'Audit Log' },
              { id: 'simulation', label: 'Simulation' },
            ]}
            active={tab}
            onChange={id => setTab(id as Tab)}
          />

          {tab === 'appointments' ? (
            <WeekCalendar
              weekStart={weekStart}
              slots={slots}
              onPrev={() => setWeekStart(w => addDays(w, -7))}
              onNext={() => setWeekStart(w => addDays(w, 7))}
              onToday={() => setWeekStart(mondayOf(new Date()))}
            />
          ) : tab === 'patients' ? (
            <PatientsTable patients={data?.recent_patients ?? []} />
          ) : tab === 'audit' ? (
            <AuditLog />
          ) : (
            <SimulationTab />
          )}
        </div>
      </main>
    </div>
  )
}
