import { useEffect, useState } from 'react'
import { CheckCircle, XCircle, Search } from 'lucide-react'
import { getCategories, getPeriods, getIntervals, validateTicker } from '../api/client'
import DateRangePicker from './DateRangePicker'

export default function AssetSelector({ onSubmit, isLoading }) {
  const [categories, setCategories] = useState({})
  const [periods,    setPeriods]    = useState([])
  const [intervals,  setIntervals]  = useState([])
  const [fetching,   setFetching]   = useState(true)
  const [fetchError, setFetchError] = useState(null)

  const [activeCategory,   setActiveCategory]   = useState(null)
  const [selectedAsset,    setSelectedAsset]    = useState(null)
  const [customSymbol,     setCustomSymbol]     = useState('')
  const [validating,       setValidating]       = useState(false)
  const [validationResult, setValidationResult] = useState(null)
  const [period,     setPeriod]    = useState(null)
  const [interval,   setInterval]  = useState(null)
  const [startDate,  setStartDate] = useState(null)
  const [endDate,    setEndDate]   = useState(null)
  const [dateErrors, setDateErrors] = useState({})

  function loadData() {
    setFetching(true)
    setFetchError(null)
    Promise.all([getCategories(), getPeriods(), getIntervals()])
      .then(([cats, per, inv]) => {
        setCategories(cats)
        setPeriods(per)
        setIntervals(inv)
        setActiveCategory(Object.keys(cats)[0])
      })
      .catch(err => setFetchError(err.message))
      .finally(() => setFetching(false))
  }

  useEffect(() => { loadData() }, [])

  function selectExample(example) {
    setSelectedAsset({
      symbol:     example.symbol,
      name:       example.name,
      asset_type: activeCategory,
      currency:   'USD',
    })
    setCustomSymbol('')
    setValidationResult(null)
  }

  async function handleValidate() {
    const sym = customSymbol.trim().toUpperCase()
    if (!sym) return
    setValidating(true)
    setValidationResult(null)
    try {
      const result = await validateTicker(sym)
      setValidationResult(result)
      if (result.valid) {
        setSelectedAsset({
          symbol:     result.info.symbol,
          name:       result.info.name,
          asset_type: result.info.type ?? 'Custom',
          currency:   result.info.currency ?? 'USD',
        })
      } else {
        setSelectedAsset(null)
      }
    } catch (err) {
      setValidationResult({ valid: false, error: err.message })
      setSelectedAsset(null)
    } finally {
      setValidating(false)
    }
  }

  function validateDates(start, end) {
    const errors = {}
    const today  = new Date().toISOString().split('T')[0]
    if (start && end) {
      if (start >= end)
        errors.end = 'End date must be after start date'
      else if (end > today)
        errors.end = 'End date cannot be in the future'
      else {
        const days = Math.round((new Date(end) - new Date(start)) / 86400000)
        if (days < 7) errors.end = 'Date range must be at least 7 days'
      }
    }
    setDateErrors(errors)
    return Object.keys(errors).length === 0
  }

  useEffect(() => {
    if (startDate && endDate) validateDates(startDate, endDate)
  }, [startDate, endDate])

  function handleStartChange(d) { setStartDate(d); if (endDate) validateDates(d, endDate) }
  function handleEndChange(d)   { setEndDate(d);   if (startDate) validateDates(startDate, d) }

  function handlePeriodChange(val) {
    setPeriod(val)
    if (val !== 'custom') { setStartDate(null); setEndDate(null); setDateErrors({}) }
  }

  function handleSubmit() {
    if (!canSubmit) return
    const config = {
      ...selectedAsset, period, interval,
      ...(period === 'custom' && { start_date: startDate, end_date: endDate }),
    }
    onSubmit(config)
  }

  const dateValid = period !== 'custom' || (startDate && endDate && Object.keys(dateErrors).length === 0)
  const canSubmit = selectedAsset && period && interval && !isLoading && dateValid
  const examples  = activeCategory ? (categories[activeCategory]?.examples ?? []) : []

  // ── Loading state ─────────────────────────────────────────────────────────

  if (fetching) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '64px 0', gap: 12, color: 'var(--text-3)' }}>
        <svg className="fp-spinner" width="20" height="20" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="8" stroke="var(--border-bright)" strokeWidth="1.5" />
          <path d="M10 2a8 8 0 0 1 8 8" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span style={{ fontSize: '13px' }}>Loading asset data…</span>
      </div>
    )
  }

  if (fetchError) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '48px 0', textAlign: 'center' }}>
        <p style={{ fontSize: '13px', color: 'var(--negative)' }}>
          Failed to load asset data: {fetchError}
        </p>
        <button className="fp-btn-ghost" onClick={loadData} style={{ padding: '8px 18px' }}>
          Retry
        </button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>

      {/* ── Category tabs — segmented control ─────────────────────────── */}
      <section>
        <span className="fp-section-label">Asset Category</span>
        <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch', scrollbarWidth: 'none' }}>
        <div className="fp-seg-control" style={{ minWidth: 'max-content' }}>
          {Object.keys(categories).map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`fp-seg-btn ${activeCategory === cat ? 'active' : ''}`}
            >
              {cat}
            </button>
          ))}
        </div>
        </div>
        {activeCategory && (
          <p style={{ marginTop: 8, fontSize: '12px', color: 'var(--text-3)' }}>
            {categories[activeCategory]?.description}
          </p>
        )}
      </section>

      {/* ── Example asset cards ────────────────────────────────────────── */}
      <section>
        <span className="fp-section-label">Select Asset</span>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
          gap: 10,
        }}>
          {examples.map(ex => {
            const isSelected = selectedAsset?.symbol === ex.symbol
            return (
              <button
                key={ex.symbol}
                onClick={() => selectExample(ex)}
                className={`fp-asset-card ${isSelected ? 'selected' : ''}`}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontWeight: 500,
                    fontSize: '13px', color: 'var(--text-1)',
                    letterSpacing: '0.03em',
                  }}>
                    {ex.symbol}
                  </span>
                  {isSelected && (
                    <CheckCircle size={13} color="var(--accent)" style={{ flexShrink: 0, marginTop: 1 }} />
                  )}
                </div>
                <span style={{ fontSize: '11px', color: 'var(--text-3)', lineHeight: 1.4, display: 'block' }}>
                  {ex.name}
                </span>
              </button>
            )
          })}
        </div>
      </section>

      {/* ── Custom ticker ──────────────────────────────────────────────── */}
      <section>
        <span className="fp-section-label">Or Enter a Custom Ticker</span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search
              size={14}
              color="var(--text-3)"
              style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
            />
            <input
              type="text"
              placeholder="e.g. TSLA, BTC-USD"
              value={customSymbol}
              onChange={e => { setCustomSymbol(e.target.value); setValidationResult(null) }}
              onKeyDown={e => e.key === 'Enter' && handleValidate()}
              className="fp-input"
              style={{
                paddingLeft: 34,
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
                textTransform: 'uppercase',
              }}
            />
          </div>
          <button
            onClick={handleValidate}
            disabled={!customSymbol.trim() || validating}
            className="fp-btn-ghost"
            style={{ padding: '8px 16px', flexShrink: 0 }}
          >
            {validating ? (
              <svg className="fp-spinner" width="13" height="13" viewBox="0 0 13 13" fill="none">
                <circle cx="6.5" cy="6.5" r="5" stroke="var(--border-bright)" strokeWidth="1.5" />
                <path d="M6.5 1.5a5 5 0 0 1 5 5" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            ) : null}
            Validate
          </button>
        </div>

        {validationResult && (
          <div style={{
            marginTop: 8,
            display: 'flex', alignItems: 'flex-start', gap: 8,
            padding: '9px 13px', borderRadius: 'var(--r-md)',
            fontSize: '13px',
            background: validationResult.valid ? 'var(--positive-dim)' : 'var(--negative-dim)',
            border: `1px solid ${validationResult.valid ? 'rgba(43,196,138,0.25)' : 'rgba(240,100,112,0.25)'}`,
            color: validationResult.valid ? 'var(--positive)' : 'var(--negative)',
          }}>
            {validationResult.valid
              ? <CheckCircle size={14} style={{ marginTop: 1, flexShrink: 0 }} />
              : <XCircle    size={14} style={{ marginTop: 1, flexShrink: 0 }} />
            }
            <span>
              {validationResult.valid
                ? `${validationResult.info.name} · ${validationResult.info.type} · ${validationResult.info.exchange}`
                : (validationResult.error ?? 'Ticker not found on Yahoo Finance')
              }
            </span>
          </div>
        )}
      </section>

      {/* ── Period ─────────────────────────────────────────────────────── */}
      <section>
        <span className="fp-section-label">Period</span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {periods.map(p => (
            <button
              key={p.value}
              onClick={() => handlePeriodChange(p.value)}
              className={`fp-pill-btn ${period === p.value ? 'active' : ''}`}
            >
              {p.label}
            </button>
          ))}
        </div>
        {period === 'custom' && (
          <DateRangePicker
            startDate={startDate}
            endDate={endDate}
            onStartChange={handleStartChange}
            onEndChange={handleEndChange}
            interval={interval}
            errors={dateErrors}
          />
        )}
      </section>

      {/* ── Interval ───────────────────────────────────────────────────── */}
      <section>
        <span className="fp-section-label">Interval</span>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {intervals.map(iv => (
            <button
              key={iv.value}
              onClick={() => setInterval(iv.value)}
              className={`fp-pill-btn ${interval === iv.value ? 'active' : ''}`}
            >
              {iv.label}
            </button>
          ))}
        </div>
      </section>

      {/* ── Selected summary ───────────────────────────────────────────── */}
      {selectedAsset && (
        <div style={{
          background: 'var(--bg-raised)', border: '1px solid var(--border-default)',
          borderRadius: 'var(--r-lg)', padding: '12px 16px',
          fontSize: '13px', color: 'var(--text-2)',
          display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, color: 'var(--text-1)' }}>
            {selectedAsset.symbol}
          </span>
          {selectedAsset.name && (
            <span style={{ color: 'var(--text-3)' }}>— {selectedAsset.name}</span>
          )}
          {period && (
            <span className="fp-badge fp-badge-neutral" style={{ marginLeft: 'auto' }}>
              {period === 'custom' && startDate && endDate
                ? `${startDate} to ${endDate}`
                : period}
            </span>
          )}
          {interval && (
            <span className="fp-badge fp-badge-neutral">{interval}</span>
          )}
        </div>
      )}

      {/* ── Run Analysis button ────────────────────────────────────────── */}
      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="fp-btn-accent"
        style={{ width: '100%', padding: '14px 24px', fontSize: '15px', borderRadius: 'var(--r-lg)' }}
      >
        {isLoading ? (
          <>
            <svg className="fp-spinner" width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="rgba(4,8,16,0.35)" strokeWidth="1.5" />
              <path d="M8 2a6 6 0 0 1 6 6" stroke="#040810" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            Running Analysis…
          </>
        ) : (
          'Run Analysis'
        )}
      </button>
    </div>
  )
}
