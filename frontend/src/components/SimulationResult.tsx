import type { SimulationResult } from '../types'

interface Props {
  result: SimulationResult
}

export default function SimulationResult({ result }: Props) {
  const passed = result.passed
  const dbPassed = result.db_passed
  const judgePassed = result.judge_passed

  return (
    <div className="space-y-6">
      {/* Verdict card */}
      <div className={`rounded-card p-6 ${passed ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
        <div className="flex items-center gap-3 mb-2">
          <span className={`text-2xl ${passed ? 'text-green-600' : 'text-red-600'}`}>
            {passed ? '✅' : '❌'}
          </span>
          <h2 className={`font-inter font-bold text-xl ${passed ? 'text-green-800' : 'text-red-800'}`}>
            {passed ? 'PASSED' : 'FAILED'}
          </h2>
        </div>
        <div className="flex gap-4 mt-3">
          <span className={`font-manrope text-sm font-bold px-3 py-1 rounded-full ${
            dbPassed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          }`}>
            DB Checks: {dbPassed ? 'PASS' : 'FAIL'}
          </span>
          <span className={`font-manrope text-sm font-bold px-3 py-1 rounded-full ${
            judgePassed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
          }`}>
            Judge: {judgePassed ? 'PASS' : 'FAIL'}
          </span>
        </div>
      </div>

      {/* Reasoning */}
      {result.reasoning && (
        <div className="bg-white rounded-card shadow-card p-6">
          <h3 className="font-inter font-medium text-ink text-lg mb-3">Evaluation</h3>
          <div className="font-manrope text-sm text-warm-700 whitespace-pre-wrap leading-relaxed">
            {result.reasoning}
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="bg-white rounded-card shadow-card p-6">
        <h3 className="font-inter font-medium text-ink text-lg mb-3">Stats</h3>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <span className="block font-manrope text-[11px] font-bold uppercase tracking-wide text-warm-500">Turns</span>
            <span className="block font-inter font-bold text-2xl text-ink mt-1">
              {result.transcript.length}
            </span>
          </div>
          <div>
            <span className="block font-manrope text-[11px] font-bold uppercase tracking-wide text-warm-500">Tool Calls</span>
            <span className="block font-inter font-bold text-2xl text-ink mt-1">
              {result.tool_calls.length}
            </span>
          </div>
          <div>
            <span className="block font-manrope text-[11px] font-bold uppercase tracking-wide text-warm-500">Duration</span>
            <span className="block font-inter font-bold text-2xl text-ink mt-1">
              {result.completed_at && result.started_at
                ? `${Math.round((new Date(result.completed_at).getTime() - new Date(result.started_at).getTime()) / 1000)}s`
                : '—'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
