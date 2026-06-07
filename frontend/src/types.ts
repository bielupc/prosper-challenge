export interface Patient {
  id: string
  first_name: string
  last_name: string
  date_of_birth: string
  phone: string | null
  email: string | null
  created_at: string
}

export interface CalendarSlot {
  id: string
  date: string
  start_time: string
  end_time: string
  is_booked: boolean
  appointment_id: string | null
  patient_name: string | null
}

export interface DashboardData {
  total_patients: number
  booked_today: number
  available_today: number
  recent_patients: Patient[]
}
