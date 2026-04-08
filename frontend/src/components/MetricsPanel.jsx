// ── Formatters ──────────────────────────────────────────────────────────────

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

// Returns 'positive' | 'negative' | 'null' | 'neutral'
function colorKey(value, key) {
  const alwaysRed   = ['max_drawdown_pct', 'worst_day_pct']
  const alwaysGreen = ['best_day_pct']
  if (alwaysRed.includes(key))   return 'negative'
  if (alwaysGreen.includes(key)) return 'positive'
  if (value == null)             return 'null'
  if (typeof value === 'number' && value > 0) return 'positive'
  if (typeof value === 'number' && value < 0) return 'negative'
  return 'neutral'
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
  annualised_return_pct: 'Ann. Return',
  volatility_pct:        'Volatility',
  sharpe_ratio:          'Sharpe Ratio',
  max_drawdown_pct:      'Max Drawdown',
  best_day_pct:          'Best Day',
  worst_day_pct:         'Worst Day',
  avg_daily_volume:      'Avg Volume',
}

const METRIC_KEYS = Object.keys(METRIC_LABELS)

const INFO_CONFIG = [
  { key: 'sector',           label: 'Sector' },
  { key: 'industry',         label: 'Industry' },
  { key: 'marketCap',        label: 'Market Cap',     fmt: fmtMarketCap },
  { key: 'trailingPE',       label: 'P/E Ratio',      fmt: v => v?.toFixed(2) },
  { key: 'fiftyTwoWeekHigh', label: '52W High',        fmt: v => v?.toFixed(2) },
  { key: 'fiftyTwoWeekLow',  label: '52W Low',         fmt: v => v?.toFixed(2) },
  { key: 'dividendYield',    label: 'Dividend Yield', fmt: v => v != null ? `${(v * 100).toFixed(2)}%` : null },
]

// ── Metric Card ──────────────────────────────────────────────────────────────

function MetricCard({ metricKey, value, animIndex }) {
  const ck    = colorKey(value, metricKey)
  const fmtd  = fmt(value, metricKey)

  const numColor = ck === 'positive' ? 'var(--positive)'
                 : ck === 'negative' ? 'var(--negative)'
                 : ck === 'null'     ? 'var(--text-3)'
                 : 'var(--text-1)'

  const numBg = ck === 'positive' ? 'var(--positive-dim)'
              : ck === 'negative' ? 'var(--negative-dim)'
              : 'transparent'

  return (
    <div
      className="fp-metric-card"
      style={{ animationDelay: `${animIndex * 0.065}s` }}
    >
      <div style={{
        fontSize: '10px', fontWeight: 600,
        letterSpacing: '0.07em', textTransform: 'uppercase',
        color: 'var(--text-3)',
        marginBottom: 10,
        fontFamily: 'var(--font-body)',
      }}>
        {METRIC_LABELS[metricKey]}
      </div>
      <div style={{
        display: 'inline-block',
        fontFamily: 'var(--font-mono)',
        fontWeight: 500,
        fontSize: '1.25rem',
        color: numColor,
        lineHeight: 1.2,
        background: numBg,
        padding: numBg !== 'transparent' ? '2px 6px' : '0',
        borderRadius: 'var(--r-sm)',
        letterSpacing: '-0.01em',
      }}>
        {fmtd}
      </div>
    </div>
  )
}

// ── MetricsPanel ─────────────────────────────────────────────────────────────

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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 700,
          fontSize: '16px', color: 'var(--text-1)',
          display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
        }}>
          <span style={{ fontFamily: 'var(--font-mono)' }}>{symbol}</span>
          {name && name !== symbol && (
            <span style={{ fontFamily: 'var(--font-body)', fontWeight: 400, fontSize: '13px', color: 'var(--text-3)' }}>
              — {name}
            </span>
          )}
        </div>
      </div>

      {/* ── Metric cards grid ──────────────────────────────────────────── */}
      <div className="fp-metrics-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {METRIC_KEYS.map((key, i) => {
          const value   = summaryStats[key] ?? null
          const fmtd    = fmt(value, key)
          const wide    = key === 'avg_daily_volume' && fmtd.length > 11
          return (
            <div key={key} style={wide ? { gridColumn: '1 / -1' } : {}}>
              <MetricCard metricKey={key} value={value} animIndex={i} />
            </div>
          )
        })}
      </div>

      {/* ── Asset info ─────────────────────────────────────────────────── */}
      {infoRows.length > 0 && (
        <div style={{
          background: 'var(--bg-surface)', border: '1px solid var(--border-default)',
          borderRadius: 'var(--r-lg)', overflow: 'hidden',
          animation: 'fp-fade-up var(--t-slow) var(--ease) both',
          animationDelay: `${METRIC_KEYS.length * 0.065 + 0.1}s`,
          opacity: 0,
        }}>
          <div style={{
            padding: '10px 14px',
            borderBottom: '1px solid var(--border-subtle)',
            background: 'var(--bg-raised)',
          }}>
            <span className="fp-section-label" style={{ margin: 0 }}>Asset Details</span>
          </div>
          <dl style={{ margin: 0 }}>
            {infoRows.map(({ label, value }, i) => (
              <div
                key={label}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                  padding: '8px 14px', gap: 8,
                  borderBottom: i < infoRows.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                }}
              >
                <dt style={{ fontSize: '12px', color: 'var(--text-3)', flexShrink: 0 }}>{label}</dt>
                <dd style={{
                  margin: 0, fontFamily: 'var(--font-mono)',
                  fontSize: '12px', fontWeight: 500, color: 'var(--text-1)',
                  textAlign: 'right',
                }}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  )
}
