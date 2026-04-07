import { useEffect } from 'react'
import { useState } from 'react'
import AssetPairSelector   from '../components/comparison/AssetPairSelector'
import ComparisonDashboard from '../components/comparison/ComparisonDashboard'
import ProgressOverlay     from '../components/ProgressOverlay'
import { usePipelineSocket } from '../hooks/usePipelineSocket'
import { X } from 'lucide-react'

export default function Compare() {
  const [view,   setView]   = useState('idle')
  const [result, setResult] = useState(null)
  const [error,  setError]  = useState(null)
  const [syms,   setSyms]   = useState({ a: '', b: '' })

  const {
    progress,
    result:              wsResult,
    error:               wsError,
    usingFallback,
    rateLimitRetryAfter: wsRateLimitRetryAfter,
    runComparison:       startComparison,
    resetResult:         wsReset,
  } = usePipelineSocket()

  useEffect(() => {
    if (!wsResult) return
    setResult(wsResult)
    setView('done')
  }, [wsResult])

  useEffect(() => {
    if (!wsError) return
    if (wsRateLimitRetryAfter !== null) return  // stay in 'loading' for rate limit countdown
    setError(wsError)
    setView('idle')
  }, [wsError, wsRateLimitRetryAfter])

  function handleSubmit(config_a, config_b) {
    setError(null)
    setView('loading')
    setSyms({ a: config_a.symbol, b: config_b.symbol })
    startComparison(config_a, config_b)
  }

  function handleReset() {
    setView('idle')
    setResult(null)
    setError(null)
    wsReset()
  }

  return (
    <div>
      {/* Error banner */}
      {error && (
        <div style={{ marginBottom: 20 }}>
          <div className="fp-error-banner">
            <span>{error}</span>
            <button onClick={() => setError(null)} aria-label="Dismiss">
              <X size={15} />
            </button>
          </div>
        </div>
      )}

      <div key={view} style={{ animation: 'fp-fade-up 0.28s var(--ease) both' }}>
        {view === 'idle' && (
          <div>
            <div style={{ marginBottom: 24 }}>
              <h2 style={{
                fontFamily: 'var(--font-display)', fontWeight: 800,
                fontSize: '1.5rem', color: 'var(--text-1)',
                margin: 0, letterSpacing: '-0.01em', lineHeight: 1.2,
              }}>
                Compare Two Assets
              </h2>
              <p style={{ color: 'var(--text-2)', marginTop: 8, fontSize: '14px' }}>
                Select two assets, run side-by-side analysis, and download a combined report.
              </p>
            </div>
            <div className="fp-card" style={{ padding: '28px' }}>
              <AssetPairSelector onSubmit={handleSubmit} isLoading={false} />
            </div>
          </div>
        )}

        {view === 'loading' && (
          <>
            <ProgressOverlay
              message={progress.message}
              percent={progress.percent}
              usingFallback={usingFallback}
              title="Comparing..."
              subtitle={syms.a && syms.b ? `${syms.a} vs ${syms.b}` : null}
              rateLimitError={wsRateLimitRetryAfter !== null}
              rateLimitRetryAfter={wsRateLimitRetryAfter}
            />
            {wsRateLimitRetryAfter !== null && (
              <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
                <button
                  className="fp-btn-secondary"
                  onClick={() => { wsReset(); setView('idle') }}
                >
                  Back to search
                </button>
              </div>
            )}
          </>
        )}

        {view === 'done' && result && (
          <ComparisonDashboard result={result} onReset={handleReset} />
        )}
      </div>
    </div>
  )
}
