import { useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { getChartUrl } from '../api/client'

const LABEL_MAP = {
  candlestick:         'Candlestick',
  price_ma:            'Price & MA',
  cumulative_return:   'Cumulative Return',
  drawdown:            'Drawdown',
  monthly_returns:     'Monthly Returns',
  summary_stats_table: 'Summary Table',
}

function stemFromFilename(filename, symbol) {
  // "AAPL_candlestick.png" → "candlestick"
  let stem = filename.replace(/\.[^.]+$/, '')    // strip extension
  if (symbol) stem = stem.replace(new RegExp(`^${symbol}_`, 'i'), '')
  return stem
}

function labelFromStem(stem) {
  if (LABEL_MAP[stem]) return LABEL_MAP[stem]
  // Fallback: replace underscores, title-case
  return stem
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function ChartImage({ filename }) {
  const [loaded, setLoaded] = useState(false)
  const url = getChartUrl(filename)

  return (
    <div className="relative w-full">
      {/* Skeleton shown until image loads */}
      {!loaded && (
        <div className="absolute inset-0 rounded-xl bg-slate-100 animate-pulse min-h-64" />
      )}
      <img
        src={url}
        alt={filename}
        onLoad={() => setLoaded(true)}
        className={`w-full rounded-xl border border-slate-200 transition-opacity duration-300 ${
          loaded ? 'opacity-100' : 'opacity-0'
        }`}
      />
    </div>
  )
}

export default function ChartViewer({ symbol, charts = [] }) {
  const [activeIdx, setActiveIdx] = useState(0)

  if (charts.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 py-12 text-center text-sm text-slate-400">
        No charts available.
      </div>
    )
  }

  const activeFilename = charts[activeIdx]
  const activeUrl      = getChartUrl(activeFilename)

  return (
    <div className="space-y-4">

      {/* ── Tab bar ────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-1 border-b border-slate-200 pb-0">
        {charts.map((filename, idx) => {
          const stem  = stemFromFilename(filename, symbol)
          const label = labelFromStem(stem)
          const active = idx === activeIdx
          return (
            <button
              key={filename}
              onClick={() => setActiveIdx(idx)}
              className={[
                'px-4 py-2 text-sm font-medium rounded-t-lg -mb-px border transition-colors',
                active
                  ? 'border-slate-200 border-b-white bg-white text-blue-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50',
              ].join(' ')}
            >
              {label}
            </button>
          )
        })}
      </div>

      {/* ── Chart image ────────────────────────────────────────────────── */}
      <ChartImage key={activeFilename} filename={activeFilename} />

      {/* ── Open full size link ────────────────────────────────────────── */}
      <div className="flex justify-end">
        <a
          href={activeUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-blue-600 transition-colors"
        >
          <ExternalLink size={13} />
          Open full size
        </a>
      </div>
    </div>
  )
}
