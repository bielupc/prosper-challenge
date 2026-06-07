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

export interface ToolCallLog {
  id: string
  tool_name: string
  arguments: Record<string, unknown> | null
  request_method: string | null
  request_path: string | null
  request_body: Record<string, unknown> | null
  response_status: number | null
  response_body: unknown
  result: Record<string, unknown> | null
  success: boolean
  error: string | null
  duration_ms: number
  created_at: string
}

export interface TranscriptMessage {
  role: string
  content: unknown
}

export interface CallSessionSummary {
  id: string
  patient_name: string | null
  status: string
  started_at: string
  ended_at: string | null
  tool_call_count: number
  failed_count: number
}

export interface CallSessionDetail {
  id: string
  patient_id: string | null
  patient_name: string | null
  status: string
  transcript: TranscriptMessage[] | null
  started_at: string
  ended_at: string | null
  tool_calls: ToolCallLog[]
}
