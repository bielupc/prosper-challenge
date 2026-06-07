import { useCallback, useEffect, useState } from 'react'
import { API_URL, headers } from '../api'
import type {
  CallSessionDetail,
  CallSessionSummary,
  ToolCallLog,
  TranscriptMessage,
} from '../types'

function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-pill px-2 py-0.5 text-[11px] font-manrope font-bold ${
        ok
          ? 'bg-prosper-blue-accent/10 text-prosper-blue-accent'
          : 'bg-prosper-orange/10 text-prosper-orange'
      }`}
    >
      {label}
    </span>
  )
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  return (
    <div>
      <p className="font-manrope text-[11px] font-bold uppercase tracking-wide text-warm-500 mb-1">
        {label}
      </p>
      <pre className="bg-cream border border-border-cream rounded-well p-2.5 text-[12px] leading-snug text-warm-700 font-mono overflow-x-auto whitespace-pre-wrap break-words">
        {text}
      </pre>
    </div>
  )
}

function ToolCallCard({ call }: { call: ToolCallLog }) {
  const [open, setOpen] = useState(false)
  const reqLine =
    call.request_method && call.request_path
      ? `${call.request_method} ${call.request_path}`
      : null

  return (
    <div className="border border-border-gray rounded-well overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-cream/60 transition-colors"
      >
        <span className="font-manrope font-bold text-sm text-ink">{call.tool_name}</span>
        <StatusBadge ok={call.success} label={call.success ? 'ok' : 'failed'} />
        {call.response_status !== null && (
          <span className="font-mono text-[11px] text-warm-500">{call.response_status}</span>
        )}
        <span className="ml-auto font-manrope text-[11px] text-warm-500">
          {formatClock(call.created_at)} · {call.duration_ms}ms
        </span>
        <span className="font-manrope text-warm-500 text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 space-y-2.5 border-t border-border-gray">
          <JsonBlock label="Arguments (from LLM)" value={call.arguments} />
          {reqLine && <JsonBlock label="API request" value={reqLine} />}
          <JsonBlock label="Request body" value={call.request_body} />
          <JsonBlock label="API response" value={call.response_body} />
          <JsonBlock label="Result to LLM" value={call.result} />
          {call.error && <JsonBlock label="Error" value={call.error} />}
        </div>
      )}
    </div>
  )
}

function messageText(content: unknown): string {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .map(part =>
        part && typeof part === 'object' && 'text' in part
          ? String((part as { text: unknown }).text)
          : typeof part === 'string'
            ? part
            : '',
      )
      .join('')
      .trim()
  }
  return ''
}

function Conversation({ transcript }: { transcript: TranscriptMessage[] | null }) {
  const turns = (transcript ?? []).filter(m => m.role === 'user' || m.role === 'assistant')
  const visible = turns.map(m => ({ role: m.role, text: messageText(m.content) })).filter(m => m.text)

  if (visible.length === 0) {
    return (
      <p className="font-manrope text-sm text-warm-500 py-6 text-center">
        No conversation captured yet.
      </p>
    )
  }

  return (
    <div className="space-y-2">
      {visible.map((m, i) => (
        <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
          <div
            className={`max-w-[85%] rounded-well px-3 py-2 font-manrope text-sm ${
              m.role === 'user'
                ? 'bg-prosper-orange/10 text-ink'
                : 'bg-cream border border-border-cream text-warm-700'
            }`}
          >
            <span className="block text-[10px] font-bold uppercase tracking-wide text-warm-500 mb-0.5">
              {m.role === 'user' ? 'Caller' : 'Agent'}
            </span>
            {m.text}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function AuditLog() {
  const [sessions, setSessions] = useState<CallSessionSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<CallSessionDetail | null>(null)

  const fetchSessions = useCallback(() => {
    fetch(`${API_URL}/audit/sessions`, { headers })
      .then(r => r.json())
      .then((rows: CallSessionSummary[]) => {
        setSessions(rows)
        setSelectedId(prev => prev ?? rows[0]?.id ?? null)
      })
      .catch(console.error)
  }, [])

  const fetchDetail = useCallback((id: string) => {
    fetch(`${API_URL}/audit/sessions/${id}`, { headers })
      .then(r => r.json())
      .then(setDetail)
      .catch(console.error)
  }, [])

  // Audit data is reviewed after the fact — fetch on mount (the tab remounts
  // this component each time it's opened) and on demand, not on a poll.
  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  useEffect(() => {
    if (selectedId) fetchDetail(selectedId)
  }, [selectedId, fetchDetail])

  const refresh = useCallback(() => {
    fetchSessions()
    if (selectedId) fetchDetail(selectedId)
  }, [fetchSessions, fetchDetail, selectedId])

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
      {/* Session list */}
      <div className="bg-white rounded-card shadow-card p-4 h-fit">
        <div className="flex items-center justify-between mb-3 px-1">
          <h2 className="font-inter font-medium text-ink text-base">Calls</h2>
          <button
            onClick={refresh}
            className="font-manrope text-xs font-bold text-prosper-orange hover:text-prosper-orange-bright transition-colors"
          >
            Refresh
          </button>
        </div>
        {sessions.length === 0 ? (
          <p className="font-manrope text-sm text-warm-500 px-1 py-4">No calls recorded yet.</p>
        ) : (
          <div className="space-y-1.5">
            {sessions.map(s => {
              const active = s.id === selectedId
              return (
                <button
                  key={s.id}
                  onClick={() => setSelectedId(s.id)}
                  className={`w-full text-left rounded-well px-3 py-2.5 transition-colors ${
                    active ? 'bg-prosper-orange/10' : 'hover:bg-cream'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-manrope font-bold text-sm text-ink truncate">
                      {s.patient_name ?? 'Unidentified caller'}
                    </span>
                    {s.status === 'active' && (
                      <span className="h-2 w-2 rounded-full bg-prosper-orange shrink-0" />
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="font-manrope text-[11px] text-warm-500">
                      {formatDateTime(s.started_at)}
                    </span>
                    <span className="font-manrope text-[11px] text-warm-500">
                      · {s.tool_call_count} {s.tool_call_count === 1 ? 'call' : 'calls'}
                    </span>
                    {s.failed_count > 0 && (
                      <span className="font-manrope text-[11px] font-bold text-prosper-orange">
                        · {s.failed_count} failed
                      </span>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Detail: tool calls side-by-side with the conversation */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="bg-white rounded-card shadow-card p-6">
          <h2 className="font-inter font-medium text-ink text-xl mb-4">Tool Calls</h2>
          {!detail || detail.tool_calls.length === 0 ? (
            <p className="font-manrope text-sm text-warm-500 py-6 text-center">
              No tool calls for this session.
            </p>
          ) : (
            <div className="space-y-2">
              {detail.tool_calls.map(c => (
                <ToolCallCard key={c.id} call={c} />
              ))}
            </div>
          )}
        </div>

        <div className="bg-white rounded-card shadow-card p-6">
          <h2 className="font-inter font-medium text-ink text-xl mb-4">Conversation</h2>
          <Conversation transcript={detail?.transcript ?? null} />
        </div>
      </div>
    </div>
  )
}
