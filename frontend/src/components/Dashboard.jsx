import { useEffect, useState } from 'react'
import { ArrowLeft, CalendarPlus, Zap, RefreshCw } from 'lucide-react'
import { listReports } from '../api/client'
import MetricsPanel from './MetricsPanel'
import ChartViewer from './ChartViewer'
import ReportDownload from './ReportDownload'
import ScheduleModal from './ScheduleModal'

export default function Dashboard({ result, cacheInfo, onReset, onRefresh }) {
  const [reports,      setReports]      = useState(null)
  const [reportsError, setReportsError] = useState(null)
  const [showSchedule, setShowSchedule] = useState(false)

  const { symbol, summary_stats, asset_info, latest_value } = result

  const name          = asset_info?.longName ?? asset_info?.shortName ?? result.name ?? symbol
  const assetType     = asset_info?.quoteType ?? result.asset_type ?? ''
  const period        = result.period     ?? ''
  const interval      = result.interval   ?? ''
  const startDate     = result.start_date ?? null
  const endDate       = result.end_date   ?? null
  const intervalLabel = interval === '1d'  ? 'Daily'
                      : interval === '1wk' ? 'Weekly'
                      : interval === '1mo' ? 'Monthly'
                      : interval

  function formatDisplayDate(dateStr) {
    return new Date(dateStr).toLocaleDateString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric',
    })
  }

  const periodChip = period === 'custom' && startDate && endDate
    ? `${formatDisplayDate(startDate)} \u2192 ${formatDisplayDate(endDate)}`
    : period

  const config = {
    symbol,
    name,
    asset_type: result.asset_type ?? assetType,
    currency:   asset_info?.currency ?? 'USD',
    period,
    interval,
    ...(period === 'custom' && startDate && endDate && { start_date: startDate, end_date: endDate }),
  }

  useEffect(() => {
    listReports(symbol)
      .then(setReports)
      .catch(err => setReportsError(err.message))
  }, [symbol])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="fp-card" style={{ padding: '20px 24px' }}>
        <div style={{
          display: 'flex', flexDirection: 'column', gap: 16,
        }}>
          {/* Top row: name + actions */}
          <div style={{
            display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
            gap: 16, flexWrap: 'wrap',
          }}>
            {/* Asset identity */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <h1 style={{
                  margin: 0,
                  fontFamily: 'var(--font-display)', fontWeight: 700,
                  fontSize: '1.3rem', color: 'var(--text-1)',
                  letterSpacing: '-0.01em', lineHeight: 1.3,
                }}>
                  {name}
                </h1>
                <span className="fp-badge fp-badge-accent">{symbol}</span>
                {assetType && (
                  <span className="fp-badge fp-badge-neutral"
                    style={{ textTransform: 'none', fontFamily: 'var(--font-body)', letterSpacing: 0 }}>
                    {assetType}
                  </span>
                )}
              </div>

              {/* Cache badge */}
              {cacheInfo?.hit && (
                <div style={{ marginTop: 6 }}>
                  <span
                    title="This report was loaded from cache. Click Refresh to fetch fresh data."
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 5,
                      fontSize: '11px', fontWeight: 600,
                      color: 'var(--positive)',
                      background: 'var(--positive-dim)',
                      border: '1px solid rgba(43,196,138,0.25)',
                      borderRadius: 'var(--r-full)', padding: '3px 9px',
                      cursor: 'default',
                    }}
                  >
                    <Zap size={11} />
                    Cached &middot; {cacheInfo.ageMinutes != null ? `${cacheInfo.ageMinutes} min ago` : 'recently'}
                  </span>
                </div>
              )}

              {/* Period + interval chips row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                {periodChip && (
                  <span style={{
                    fontSize: '11px', fontWeight: 500,
                    background: 'var(--bg-raised)', border: '1px solid var(--border-default)',
                    borderRadius: 'var(--r-full)', padding: '3px 10px',
                    color: 'var(--text-2)', fontFamily: 'var(--font-mono)',
                  }}>
                    {periodChip}
                  </span>
                )}
                {intervalLabel && (
                  <span style={{
                    fontSize: '11px', fontWeight: 500,
                    background: 'var(--bg-raised)', border: '1px solid var(--border-default)',
                    borderRadius: 'var(--r-full)', padding: '3px 10px',
                    color: 'var(--text-2)', fontFamily: 'var(--font-mono)',
                  }}>
                    {intervalLabel}
                  </span>
                )}
                {latest_value?.close != null && (
                  <span style={{
                    fontSize: '12px', color: 'var(--text-2)', marginLeft: 4,
                  }}>
                    Latest close:{' '}
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, color: 'var(--text-1)' }}>
                      {latest_value.close.toFixed(2)}
                    </span>
                    {latest_value.date && (
                      <span style={{ color: 'var(--text-3)', marginLeft: 4 }}>
                        ({latest_value.date})
                      </span>
                    )}
                  </span>
                )}
              </div>
            </div>

            {/* Action buttons */}
            <div className="fp-dash-actions" style={{ display: 'flex', gap: 8, flexShrink: 0, flexWrap: 'wrap' }}>
              <button
                onClick={() => setShowSchedule(true)}
                className="fp-btn-primary"
                style={{ padding: '8px 16px' }}
              >
                <CalendarPlus size={14} />
                Schedule Report
              </button>
              {onRefresh && (
                <button
                  onClick={() => onRefresh(config)}
                  className="fp-btn-ghost"
                  title="Bypass cache and fetch fresh data"
                  style={{ padding: '8px 16px' }}
                >
                  <RefreshCw size={14} />
                  Refresh
                </button>
              )}
              <button
                onClick={onReset}
                className="fp-btn-ghost"
                style={{ padding: '8px 16px' }}
              >
                <ArrowLeft size={14} />
                Analyse another
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Main grid ──────────────────────────────────────────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 20,
      }} className="dashboard-grid">
        <div style={{ gridColumn: '1 / 2' }}>
          <MetricsPanel
            summaryStats={summary_stats}
            assetInfo={asset_info}
            symbol={symbol}
            name={name}
          />
        </div>
        <div style={{ gridColumn: '2 / 4' }}>
          {reports === null && !reportsError && (
            <div className="fp-card" style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '64px 0', gap: 10, color: 'var(--text-3)',
            }}>
              <svg className="fp-spinner" width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="7" stroke="var(--border-bright)" strokeWidth="1.5" />
                <path d="M9 2a7 7 0 0 1 7 7" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <span style={{ fontSize: '13px' }}>Loading charts…</span>
            </div>
          )}
          {reportsError && (
            <div style={{
              background: 'var(--negative-dim)', border: '1px solid rgba(240,100,112,0.25)',
              borderRadius: 'var(--r-lg)', padding: '14px 18px',
              fontSize: '13px', color: 'var(--negative)',
            }}>
              Failed to load charts: {reportsError}
            </div>
          )}
          {reports && (
            reports.charts.length === 0 ? (
              <div className="fp-card" style={{
                padding: '48px', textAlign: 'center',
                fontSize: '13px', color: 'var(--text-3)',
              }}>
                Charts are still generating — refresh in a moment.
              </div>
            ) : (
              <ChartViewer symbol={symbol} charts={reports.charts} />
            )
          )}
        </div>
      </div>

      {/* ── Report download ────────────────────────────────────────────── */}
      <ReportDownload
        symbol={symbol}
        name={name}
        hasPdf={reports?.has_pdf ?? false}
      />

      {/* ── Schedule modal ─────────────────────────────────────────────── */}
      {showSchedule && (
        <ScheduleModal
          config={config}
          symbol={symbol}
          name={name}
          onClose={() => setShowSchedule(false)}
        />
      )}

      <style>{`
        @media (max-width: 767px) {
          .fp-dash-actions { width: 100%; }
          .fp-dash-actions button { flex: 1; justify-content: center; }
        }
      `}</style>
    </div>
  )
}
