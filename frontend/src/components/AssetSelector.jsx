import { useEffect, useState } from 'react'
import { CheckCircle, XCircle, Loader2, Search } from 'lucide-react'
import { getCategories, getPeriods, getIntervals, validateTicker } from '../api/client'

export default function AssetSelector({ onSubmit, isLoading }) {
  const [categories, setCategories] = useState({})
  const [periods, setPeriods]       = useState([])
  const [intervals, setIntervals]   = useState([])
  const [fetching, setFetching]     = useState(true)
  const [fetchError, setFetchError] = useState(null)

  const [activeCategory, setActiveCategory] = useState(null)
  const [selectedAsset, setSelectedAsset]   = useState(null) // { symbol, name, asset_type, currency }

  const [customSymbol, setCustomSymbol]   = useState('')
  const [validating, setValidating]       = useState(false)
  const [validationResult, setValidationResult] = useState(null) // { valid, info?, error? }

  const [period, setPeriod]     = useState(null)
  const [interval, setInterval] = useState(null)

  // ── Load reference data ──────────────────────────────────────────────────

  useEffect(() => {
    Promise.all([getCategories(), getPeriods(), getIntervals()])
      .then(([cats, per, inv]) => {
        setCategories(cats)
        setPeriods(per)
        setIntervals(inv)
        setActiveCategory(Object.keys(cats)[0])
      })
      .catch(err => setFetchError(err.message))
      .finally(() => setFetching(false))
  }, [])

  // ── Handlers ─────────────────────────────────────────────────────────────

  function selectExample(example) {
    setSelectedAsset({
      symbol:     example.symbol,
      name:       example.name,
      asset_type: activeCategory,
      currency:   'USD', // will be resolved by validate_ticker during pipeline run
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

  function handleSubmit() {
    if (!selectedAsset || !period || !interval || isLoading) return
    onSubmit({ ...selectedAsset, period, interval })
  }

  // ── Derived state ─────────────────────────────────────────────────────────

  const canSubmit = selectedAsset && period && interval && !isLoading
  const examples  = activeCategory ? (categories[activeCategory]?.examples ?? []) : []

  // ── Render ────────────────────────────────────────────────────────────────

  if (fetching) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500">
        <Loader2 className="animate-spin mr-2" size={22} />
        Loading asset data…
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="rounded-lg bg-red-50 border border-red-200 text-red-700 px-5 py-4 text-sm">
        Failed to load asset data: {fetchError}
      </div>
    )
  }

  return (
    <div className="space-y-8">

      {/* ── Category tabs ──────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          Asset Category
        </h2>
        <div className="flex flex-wrap gap-2">
          {Object.keys(categories).map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={[
                'px-4 py-2 rounded-full text-sm font-medium transition-colors',
                activeCategory === cat
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              ].join(' ')}
            >
              {cat}
            </button>
          ))}
        </div>
        {activeCategory && (
          <p className="mt-2 text-xs text-slate-400">
            {categories[activeCategory]?.description}
          </p>
        )}
      </section>

      {/* ── Example asset cards ────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          Select Asset
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {examples.map(ex => {
            const isSelected = selectedAsset?.symbol === ex.symbol
            return (
              <button
                key={ex.symbol}
                onClick={() => selectExample(ex)}
                className={[
                  'text-left rounded-xl border p-4 transition-all',
                  isSelected
                    ? 'border-blue-500 bg-blue-50 shadow-sm ring-1 ring-blue-500'
                    : 'border-slate-200 bg-white hover:border-blue-300 hover:shadow-sm',
                ].join(' ')}
              >
                <span className="block font-mono font-semibold text-slate-800 text-sm">
                  {ex.symbol}
                </span>
                <span className="block text-xs text-slate-500 mt-0.5 leading-tight">
                  {ex.name}
                </span>
                {isSelected && (
                  <CheckCircle size={14} className="mt-2 text-blue-500" />
                )}
              </button>
            )
          })}
        </div>
      </section>

      {/* ── Custom ticker ──────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          Or Enter a Custom Ticker
        </h2>
        <div className="flex gap-2 items-start">
          <div className="relative flex-1 max-w-xs">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="e.g. TSLA, BTC-USD"
              value={customSymbol}
              onChange={e => {
                setCustomSymbol(e.target.value)
                setValidationResult(null)
              }}
              onKeyDown={e => e.key === 'Enter' && handleValidate()}
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 text-sm
                         focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
            />
          </div>
          <button
            onClick={handleValidate}
            disabled={!customSymbol.trim() || validating}
            className="px-4 py-2 rounded-lg bg-slate-800 text-white text-sm font-medium
                       hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors flex items-center gap-1.5"
          >
            {validating && <Loader2 size={14} className="animate-spin" />}
            Validate
          </button>
        </div>

        {validationResult && (
          <div className={[
            'mt-2 flex items-start gap-2 text-sm rounded-lg px-3 py-2',
            validationResult.valid
              ? 'bg-green-50 text-green-700 border border-green-200'
              : 'bg-red-50 text-red-700 border border-red-200',
          ].join(' ')}>
            {validationResult.valid
              ? <CheckCircle size={15} className="mt-0.5 shrink-0" />
              : <XCircle    size={15} className="mt-0.5 shrink-0" />
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
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          Period
        </h2>
        <div className="flex flex-wrap gap-2">
          {periods.map(p => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value)}
              className={[
                'px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors',
                period === p.value
                  ? 'border-blue-500 bg-blue-50 text-blue-700'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-slate-400',
              ].join(' ')}
            >
              {p.label}
            </button>
          ))}
        </div>
      </section>

      {/* ── Interval ───────────────────────────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
          Interval
        </h2>
        <div className="flex flex-wrap gap-2">
          {intervals.map(iv => (
            <button
              key={iv.value}
              onClick={() => setInterval(iv.value)}
              className={[
                'px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors',
                interval === iv.value
                  ? 'border-blue-500 bg-blue-50 text-blue-700'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-slate-400',
              ].join(' ')}
            >
              {iv.label}
            </button>
          ))}
        </div>
      </section>

      {/* ── Selected summary ───────────────────────────────────────────── */}
      {selectedAsset && (
        <div className="rounded-xl bg-slate-50 border border-slate-200 px-5 py-4 text-sm text-slate-700">
          <span className="font-semibold text-slate-900">{selectedAsset.symbol}</span>
          {' · '}{selectedAsset.name}
          {period   && <span className="ml-3 text-slate-500">Period: <strong>{period}</strong></span>}
          {interval && <span className="ml-3 text-slate-500">Interval: <strong>{interval}</strong></span>}
        </div>
      )}

      {/* ── Run button ─────────────────────────────────────────────────── */}
      <button
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="w-full py-3 rounded-xl bg-blue-600 text-white font-semibold text-sm
                   hover:bg-blue-700 active:bg-blue-800
                   disabled:opacity-40 disabled:cursor-not-allowed
                   transition-colors flex items-center justify-center gap-2"
      >
        {isLoading && <Loader2 size={16} className="animate-spin" />}
        {isLoading ? 'Running Analysis…' : 'Run Analysis'}
      </button>
    </div>
  )
}
