import { useEffect, useState } from 'react'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { listReports } from '../api/client'
import MetricsPanel from './MetricsPanel'
import ChartViewer from './ChartViewer'
import ReportDownload from './ReportDownload'

export default function Dashboard({ result, onReset }) {
  const [reports, setReports]       = useState(null)
  const [reportsError, setReportsError] = useState(null)

  const { symbol, summary_stats, asset_info, latest_value } = result

  // Derive display fields from asset_info or fallback to result fields
  const name       = asset_info?.longName ?? asset_info?.shortName ?? result.name ?? symbol
  const assetType  = asset_info?.quoteType ?? result.asset_type ?? ''
  const period     = result.period  ?? ''
  const interval   = result.interval ?? ''

  const periodLabel   = period
  const intervalLabel = interval === '1d' ? 'Daily' : interval === '1wk' ? 'Weekly' : interval === '1mo' ? 'Monthly' : interval

  useEffect(() => {
    listReports(symbol)
      .then(setReports)
      .catch(err => setReportsError(err.message))
  }, [symbol])

  return (
    <div className="space-y-6">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="rounded-xl border border-slate-200 bg-white px-6 py-5
                      flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900 truncate">
              {name}
              <span className="ml-2 text-slate-400 font-normal">({symbol})</span>
            </h1>
            {assetType && (
              <span className="px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs font-medium border border-blue-200">
                {assetType}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {periodLabel && intervalLabel
              ? `${periodLabel} · ${intervalLabel}`
              : periodLabel || intervalLabel}
            {latest_value?.close != null && (
              <span className="ml-3 text-slate-700 font-medium">
                Latest close: {latest_value.close.toFixed(2)}
                {latest_value.date && (
                  <span className="ml-1 text-slate-400 font-normal">({latest_value.date})</span>
                )}
              </span>
            )}
          </p>
        </div>
        <button
          onClick={onReset}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-slate-300
                     text-sm font-medium text-slate-600 bg-white hover:bg-slate-50
                     transition-colors shrink-0"
        >
          <ArrowLeft size={15} />
          Analyse another asset
        </button>
      </div>

      {/* ── Main grid: MetricsPanel + ChartViewer ──────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-1">
          <MetricsPanel
            summaryStats={summary_stats}
            assetInfo={asset_info}
            symbol={symbol}
            name={name}
          />
        </div>
        <div className="md:col-span-2">
          {reports === null && !reportsError && (
            <div className="flex items-center justify-center py-20 text-slate-400">
              <Loader2 className="animate-spin mr-2" size={20} />
              Loading charts…
            </div>
          )}
          {reportsError && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
              Failed to load charts: {reportsError}
            </div>
          )}
          {reports && (
            <ChartViewer symbol={symbol} charts={reports.charts} />
          )}
        </div>
      </div>

      {/* ── Report download ────────────────────────────────────────────── */}
      <ReportDownload
        symbol={symbol}
        name={name}
        hasPdf={reports?.has_pdf ?? false}
      />
    </div>
  )
}
