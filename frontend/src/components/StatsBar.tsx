import type { DashboardData } from '../types'

interface Props {
  data: DashboardData | null
}

function StatCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="bg-white rounded-card shadow-card p-6">
      <p className="font-inter font-bold text-[39px] leading-[48px] text-ink">
        {value ?? '—'}
      </p>
      <div className="h-[3px] w-8 bg-prosper-orange rounded-full mt-1 mb-2" />
      <p className="font-manrope text-warm-600 text-sm">{label}</p>
    </div>
  )
}

export default function StatsBar({ data }: Props) {
  return (
    <div className="grid grid-cols-3 gap-6">
      <StatCard label="Total Patients" value={data?.total_patients} />
      <StatCard label="Appointments Today" value={data?.booked_today} />
      <StatCard label="Available Slots Today" value={data?.available_today} />
    </div>
  )
}
