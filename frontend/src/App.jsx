import { useState, useEffect } from 'react'
import { BarChart2, Loader2, X, Clock, ChevronRight } from 'lucide-react'
import AssetSelector from './components/AssetSelector'
import Dashboard from './components/Dashboard'
import { runPipeline, getPreviousRuns, listReports } from './api/client'
import './App.css'

// ── Previous Runs Modal ────────────────────────────────────────────────────

function PreviousRunsModal({ onClose, onSelect }) {
  const [runs, setRuns]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)
  const [selecting, setSelecting] = useState(null)

  useEffect(() => {
    getPreviousRuns()
      .then(setRuns)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  async function handleSelect(run) {
    setSelecting(run.symbol)
    try {
      const reports = await listReports(run.symbol)
      onSelect(run, reports)
    } catch {
      setSelecting(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
         onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h2 className="font-semibold text-slate-900 flex items-center gap-2">
            <Clock size={16} className="text-slate-400" /> Previous Runs
          </h2>
          <button onClick={onClose}
                  className="text-slate-400 hover:text-slate-600 transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 px-2 py-2">
          {loading && (
            <div className="flex items-center justify-center py-12 text-slate-400">
              <Loader2 className="animate-spin mr-2" size={18} /> Loading…
            </div>
          )}
          {error && (
            <p className="text-sm text-red-600 px-4 py-3">{error}</p>
          )}
          {runs?.length === 0 && (
            <p className="text-sm text-slate-400 px-4 py-3">No previous runs found.</p>
          )}
          {runs?.map((run, i) => (
            <button key={i} onClick={() => handleSelect(run)}
                    disabled={selecting === run.symbol}
                    className="w-full text-left flex items-center justify-between
                               px-4 py-3 rounded-xl hover:bg-slate-50 transition-colors group">
              <div>
                <p className="font-medium text-slate-800">
                  {run.symbol}
                  {run.name && <span className="ml-2 text-slate-400 font-normal text-sm">— {run.name}</span>}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {run.asset_type} · {new Date(run.run_at).toLocaleString()}
                  {run.row_count != null && ` · ${run.row_count.toLocaleString()} rows`}
                </p>
              </div>
              {selecting === run.symbol
                ? <Loader2 size={15} className="animate-spin text-slate-400 shrink-0" />
                : <ChevronRight size={15} className="text-slate-300 group-hover:text-slate-500 shrink-0" />
              }
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Loading overlay ────────────────────────────────────────────────────────

function LoadingOverlay({ message }) {
  return (
    <div className="flex items-center justify-center py-24">
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm px-10 py-10
                      flex flex-col items-center gap-5 text-center max-w-sm w-full">
        <Loader2 size={40} className="animate-spin text-blue-600" />
        <div>
          <p className="font-semibold text-slate-800">{message}</p>
          <p className="text-sm text-slate-400 mt-1">This usually takes 10–20 seconds.</p>
        </div>
      </div>
    </div>
  )
}

// ── App ────────────────────────────────────────────────────────────────────

export default function App() {
  const [view, setView]           = useState('idle')
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState(null)
  const [loadingMsg, setLoadingMsg] = useState('')
  const [showRuns, setShowRuns]   = useState(false)

  async function handleSubmit(config) {
    setError(null)
    setView('loading')
    setLoadingMsg(`Fetching data for ${config.symbol}…`)
    try {
      const data = await runPipeline(config)
      // Stitch config fields into result so Dashboard can access period/interval
      setResult({ ...data, period: config.period, interval: config.interval })
      setView('done')
    } catch (err) {
      setError(err.message)
      setView('idle')
    }
  }

  function handlePreviousRunSelect(run, reports) {
    // Reconstruct a minimal result object from the stored run record
    setResult({
      status:       'success',
      symbol:       run.symbol,
      summary_stats: {},
      chart_urls:   reports.charts.map(f => `/api/reports/charts/${f}`),
      latest_value: null,
      asset_info:   {},
      period:       run.period  ?? '',
      interval:     run.interval ?? '',
      _fromHistory: true,
    })
    setShowRuns(false)
    setView('done')
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ── Navbar ───────────────────────────────────────────────────────── */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-[1200px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <BarChart2 size={20} className="text-blue-600" />
            <span className="font-semibold text-slate-900">Financial Pipeline</span>
            <span className="hidden sm:block text-slate-300">·</span>
            <span className="hidden sm:block text-sm text-slate-400">Powered by Yahoo Finance</span>
          </div>
          <button
            onClick={() => setShowRuns(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border
                       border-slate-200 text-sm text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <Clock size={14} />
            Previous runs
          </button>
        </div>
      </header>

      {/* ── Error banner ─────────────────────────────────────────────────── */}
      {error && (
        <div className="max-w-[1200px] mx-auto px-6 pt-4">
          <div className="flex items-start justify-between gap-3 rounded-xl border border-red-200
                          bg-red-50 px-4 py-3 text-sm text-red-700">
            <span>{error}</span>
            <button onClick={() => setError(null)}
                    className="text-red-400 hover:text-red-600 shrink-0 transition-colors">
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <main className="max-w-[1200px] mx-auto px-6 py-8">
        {view === 'idle' && (
          <div className="max-w-3xl mx-auto">
            <div className="mb-8">
              <h1 className="text-2xl font-bold text-slate-900">Run a Financial Analysis</h1>
              <p className="text-slate-500 mt-1 text-sm">
                Select an asset, configure the date range, and generate charts and metrics.
              </p>
            </div>
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm px-6 py-8">
              <AssetSelector onSubmit={handleSubmit} isLoading={false} />
            </div>
          </div>
        )}

        {view === 'loading' && <LoadingOverlay message={loadingMsg} />}

        {view === 'done' && result && (
          <Dashboard result={result} onReset={() => { setView('idle'); setResult(null) }} />
        )}
      </main>

      {/* ── Previous runs modal ──────────────────────────────────────────── */}
      {showRuns && (
        <PreviousRunsModal
          onClose={() => setShowRuns(false)}
          onSelect={handlePreviousRunSelect}
        />
      )}
    </div>
  )
}
