function fmt(value, key) {
  if (value == null) return 'N/A'
  const pctKeys = [
    'total_return_pct', 'annualised_return_pct', 'volatility_pct',
    'max_drawdown_pct', 'best_day_pct', 'worst_day_pct',
  ]
  if (pctKeys.includes(key)) return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  if (key === 'sharpe_ratio')    return value.toFixed(2)
  if (key === 'avg_daily_volume') return value == null ? 'N/A' : value.toLocaleString()
  return String(value)
}

function color(value, key) {
  const alwaysRed   = ['max_drawdown_pct', 'worst_day_pct']
  const alwaysGreen = ['best_day_pct']
  if (alwaysRed.includes(key))   return 'text-red-600'
  if (alwaysGreen.includes(key)) return 'text-green-600'
  if (value == null)             return 'text-slate-400'
  if (typeof value === 'number' && value > 0) return 'text-green-600'
  if (typeof value === 'number' && value < 0) return 'text-red-600'
  return 'text-slate-900'
}

function fmtMarketCap(v) {
  if (v == null) return null
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(1)}B`
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(1)}M`
  return `$${v.toLocaleString()}`
}

const METRIC_LABELS = {
  total_return_pct:      'Total Return',
  annualised_return_pct: 'Annualised Return',
  volatility_pct:        'Volatility',
  sharpe_ratio:          'Sharpe Ratio',
  max_drawdown_pct:      'Max Drawdown',
  best_day_pct:          'Best Day',
  worst_day_pct:         'Worst Day',
  avg_daily_volume:      'Avg Daily Volume',
}

const METRIC_KEYS = Object.keys(METRIC_LABELS)

const INFO_CONFIG = [
  { key: 'sector',           label: 'Sector' },
  { key: 'industry',         label: 'Industry' },
  { key: 'marketCap',        label: 'Market Cap',     fmt: fmtMarketCap },
  { key: 'trailingPE',       label: 'P/E Ratio',      fmt: v => v?.toFixed(2) },
  { key: 'fiftyTwoWeekHigh', label: '52-Week High',   fmt: v => v?.toFixed(2) },
  { key: 'fiftyTwoWeekLow',  label: '52-Week Low',    fmt: v => v?.toFixed(2) },
  { key: 'dividendYield',    label: 'Dividend Yield', fmt: v => v != null ? `${(v * 100).toFixed(2)}%` : null },
]

function MetricCard({ metricKey, value }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 flex flex-col gap-1">
      <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">
        {METRIC_LABELS[metricKey]}
      </span>
      <span className={`text-xl font-bold tabular-nums ${color(value, metricKey)}`}>
        {fmt(value, metricKey)}
      </span>
    </div>
  )
}

export default function MetricsPanel({ summaryStats = {}, assetInfo = {}, symbol, name }) {
  const infoRows = INFO_CONFIG
    .map(cfg => {
      const raw = assetInfo[cfg.key]
      if (raw == null) return null
      const formatted = cfg.fmt ? cfg.fmt(raw) : String(raw)
      if (formatted == null) return null
      return { label: cfg.label, value: formatted }
    })
    .filter(Boolean)

  return (
    <div className="space-y-6">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div>
        <h2 className="text-lg font-semibold text-slate-900">
          {symbol}
          {name && <span className="ml-2 text-slate-400 font-normal text-base">— {name}</span>}
        </h2>
      </div>

      {/* ── Metric cards ───────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {METRIC_KEYS.map(key => (
          <MetricCard key={key} metricKey={key} value={summaryStats[key] ?? null} />
        ))}
      </div>

      {/* ── Asset info ─────────────────────────────────────────────────── */}
      {infoRows.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
              Asset Details
            </span>
          </div>
          <dl className="divide-y divide-slate-100">
            {infoRows.map(({ label, value }) => (
              <div key={label} className="flex justify-between px-4 py-2.5 text-sm">
                <dt className="text-slate-500">{label}</dt>
                <dd className="font-medium text-slate-900 text-right">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  )
}
