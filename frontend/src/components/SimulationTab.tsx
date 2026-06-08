import { useCallback, useEffect, useRef, useState } from 'react'
import { API_URL, headers } from '../api'
import SimulationResult from './SimulationResult'
import type { ScenarioSummary, SimTurn, SimulationResult as SimResult } from '../types'

export default function SimulationTab() {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([])
  const [selected, setSelected] = useState('')
  const [running, setRunning] = useState(false)
  const [transcript, setTranscript] = useState<SimTurn[]>([])
  const [result, setResult] = useState<SimResult | null>(null)
  const [status, setStatus] = useState('')
  const [resetting, setResetting] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch(`${API_URL}/simulate/scenarios`, { headers })
      .then(r => r.json())
      .then(setScenarios)
      .catch(console.error)
  }, [])

  // Auto-scroll to bottom of transcript
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [transcript])

  const run = useCallback(async () => {
    if (!selected) return
    setRunning(true)
    setTranscript([])
    setResult(null)
    setStatus('Starting simulation...')

    try {
      // 1. Start simulation
      const { sim_id } = await fetch(`${API_URL}/simulate/run`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: selected }),
      }).then(r => r.json())

      setStatus('Connected — running conversation...')

      // 2. Stream events via SSE
      const es = new EventSource(`${API_URL}/simulate/stream/${sim_id}`)
      
      es.onmessage = (e) => {
        const data = JSON.parse(e.data)
        if (data.type === 'turn') {
          setTranscript(prev => [...prev, {
            role: data.role,
            text: data.text,
            timestamp: new Date().toISOString(),
          }])
        } else if (data.type === 'complete') {
          setResult(data.result)
          setRunning(false)
          setStatus('')
          es.close()
        }
      }

      es.onerror = () => {
        es.close()
        setRunning(false)
        setStatus('Stream error')
      }
    } catch (err) {
      console.error(err)
      setRunning(false)
      setStatus('Failed to start simulation')
    }
  }, [selected])

  const reset = useCallback(async () => {
    setResetting(true)
    setStatus('Resetting simulation data...')
    try {
      const { deleted_patients } = await fetch(`${API_URL}/simulate/reset`, {
        method: 'POST',
        headers,
      }).then(r => r.json())
      setTranscript([])
      setResult(null)
      setStatus(`Reset complete — removed ${deleted_patients} patient(s).`)
    } catch (err) {
      console.error(err)
      setStatus('Failed to reset simulation data')
    } finally {
      setResetting(false)
    }
  }, [])

  return (
    <div className="space-y-6">
      {/* Header / Controls */}
      <div className="bg-white rounded-card shadow-card p-6">
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <label className="block font-manrope font-bold text-sm text-ink mb-2">
              Scenario
            </label>
            <select
              value={selected}
              onChange={e => setSelected(e.target.value)}
              disabled={running}
              className="w-full bg-cream border border-border-cream rounded-btn px-4 py-2.5 font-manrope text-sm text-ink focus:outline-none focus:ring-2 focus:ring-prosper-orange/20"
            >
              <option value="">Select a scenario...</option>
              {scenarios.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          <button
            onClick={run}
            disabled={running || !selected}
            className={`mt-6 px-6 py-2.5 rounded-btn font-manrope font-bold text-sm transition-all ${
              running || !selected
                ? 'bg-warm-500/20 text-warm-500 cursor-not-allowed'
                : 'bg-prosper-orange text-white hover:bg-prosper-orange-bright shadow-chip'
            }`}
          >
            {running ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Running...
              </span>
            ) : (
              'Run Simulation'
            )}
          </button>
          <button
            onClick={reset}
            disabled={running || resetting}
            title="Delete the simulation patient(s) and free their slots"
            className={`mt-6 px-5 py-2.5 rounded-btn font-manrope font-bold text-sm transition-all border ${
              running || resetting
                ? 'border-border-cream text-warm-500 cursor-not-allowed'
                : 'border-border-cream text-warm-700 hover:bg-cream'
            }`}
          >
            {resetting ? 'Resetting...' : 'Reset Data'}
          </button>
        </div>
        {status && (
          <p className="mt-2 font-manrope text-sm text-prosper-blue-accent">{status}</p>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Live transcript */}
        <div className="bg-white rounded-card shadow-card p-6">
          <h2 className="font-inter font-medium text-ink text-xl mb-4">Conversation</h2>
          {transcript.length === 0 && !running ? (
            <p className="font-manrope text-sm text-warm-500 py-8 text-center">
              Select a scenario and click Run to start a simulation.
            </p>
          ) : (
            <div
              ref={scrollRef}
              className="space-y-3 max-h-[500px] overflow-y-auto pr-2"
            >
              {transcript.map((turn, i) => (
                <div
                  key={i}
                  className={`flex ${turn.role === 'patient' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] rounded-well px-4 py-3 font-manrope text-sm ${
                      turn.role === 'patient'
                        ? 'bg-prosper-orange/10 text-ink'
                        : 'bg-cream border border-border-cream text-warm-700'
                    }`}
                  >
                    <span className="block text-[10px] font-bold uppercase tracking-wide text-warm-500 mb-1">
                      {turn.role === 'patient' ? 'Patient' : 'Agent'}
                    </span>
                    {turn.text}
                  </div>
                </div>
              ))}
              {running && (
                <div className="flex justify-start">
                  <div className="bg-cream border border-border-cream rounded-well px-4 py-2">
                    <span className="flex gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-warm-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-1.5 h-1.5 rounded-full bg-warm-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-1.5 h-1.5 rounded-full bg-warm-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Results */}
        <div>
          {result ? (
            <SimulationResult result={result} />
          ) : running ? (
            <div className="bg-white rounded-card shadow-card p-6">
              <h2 className="font-inter font-medium text-ink text-xl mb-4">Results</h2>
              <p className="font-manrope text-sm text-warm-500">
                Waiting for simulation to complete...
              </p>
            </div>
          ) : (
            <div className="bg-white rounded-card shadow-card p-6">
              <h2 className="font-inter font-medium text-ink text-xl mb-4">Results</h2>
              <p className="font-manrope text-sm text-warm-500">
                Run a simulation to see evaluation results here.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
