import { useState } from 'react'
import { X, CalendarCheck, CheckCircle } from 'lucide-react'
import { addSchedule } from '../api/client'

const DAYS_OF_WEEK = [
  { value: 'mon', label: 'Monday' },
  { value: 'tue', label: 'Tuesday' },
  { value: 'wed', label: 'Wednesday' },
  { value: 'thu', label: 'Thursday' },
  { value: 'fri', label: 'Friday' },
  { value: 'sat', label: 'Saturday' },
  { value: 'sun', label: 'Sunday' },
]

const HOURS = Array.from({ length: 24 }, (_, i) => ({
  value: i,
  label: String(i).padStart(2, '0'),
}))

const MINUTES = [
  { value: 0,  label: '00' },
  { value: 30, label: '30' },
]

const DAYS_OF_MONTH = Array.from({ length: 28 }, (_, i) => ({
  value: i + 1,
  label: String(i + 1),
}))

function schedulePreview({ symbol, frequency, hour, minute, dayOfWeek, day }) {
  const hm = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')} (London time)`

  if (frequency === 'daily')
    return `You will receive a report for ${symbol} every day at ${hm}.`
  if (frequency === 'weekly') {
    const dow = DAYS_OF_WEEK.find(d => d.value === dayOfWeek)?.label ?? dayOfWeek
    return `You will receive a report for ${symbol} every ${dow} at ${hm}.`
  }
  if (frequency === 'monthly')
    return `You will receive a report for ${symbol} on day ${day} of every month at ${hm}.`
  return ''
}

function FormLabel({ children }) {
  return (
    <label style={{
      display: 'block',
      fontSize: '11px', fontWeight: 600,
      letterSpacing: '0.07em', textTransform: 'uppercase',
      color: 'var(--text-3)', marginBottom: 7,
      fontFamily: 'var(--font-body)',
    }}>
      {children}
    </label>
  )
}

export default function ScheduleModal({ config, symbol, name, onClose }) {
  const [email,     setEmail]     = useState('')
  const [frequency, setFrequency] = useState('daily')
  const [hour,      setHour]      = useState(8)
  const [minute,    setMinute]    = useState(0)
  const [dayOfWeek, setDayOfWeek] = useState('mon')
  const [day,       setDay]       = useState(1)

  const [submitting, setSubmitting] = useState(false)
  const [error,      setError]      = useState(null)
  const [success,    setSuccess]    = useState(null)

  const preview = schedulePreview({ symbol, frequency, hour, minute, dayOfWeek, day })

  async function handleSubmit() {
    setError(null)
    setSubmitting(true)
    try {
      // Send the user's typed hour/minute directly — the scheduler runs in
      // Europe/London timezone and interprets these values as London local time.
      const payload = {
        config,
        email,
        frequency,
        hour,
        minute,
        ...(frequency === 'weekly'  && { day_of_week: dayOfWeek }),
        ...(frequency === 'monthly' && { day }),
      }
      const res = await addSchedule(payload)
      setSuccess({ next_run: res.next_run })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fp-modal-backdrop"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="fp-modal-panel" style={{ width: '100%', maxWidth: 460 }}>

        {/* ── Header ─────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '18px 24px',
          borderBottom: '1px solid var(--border-subtle)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 'var(--r-md)',
              background: 'var(--accent-dim)', border: '1px solid rgba(79,172,247,0.22)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <CalendarCheck size={15} color="var(--accent)" />
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '15px', color: 'var(--text-1)' }}>
                Schedule Report
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-3)', marginTop: 1 }}>
                {name ?? symbol}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: 6,
              color: 'var(--text-3)', borderRadius: 'var(--r-sm)',
              lineHeight: 1, transition: 'color var(--t-fast) var(--ease)',
            }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-1)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-3)'}
          >
            <X size={17} />
          </button>
        </div>

        {/* ── Body ───────────────────────────────────────────────────── */}
        <div style={{ padding: '24px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 20 }}>

          {success ? (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              gap: 14, padding: '24px 0', textAlign: 'center',
            }}>
              <div style={{
                width: 56, height: 56, borderRadius: '50%',
                background: 'var(--positive-dim)', border: '1px solid rgba(43,196,138,0.3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <CheckCircle size={26} color="var(--positive)" />
              </div>
              <div>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '16px', color: 'var(--text-1)', marginBottom: 6 }}>
                  Report Scheduled!
                </div>
                <p style={{ margin: '0 0 8px', fontSize: '13px', color: 'var(--text-2)' }}>
                  A secret access token has been saved to your browser.
                  You can manage this report from the Scheduled Reports panel.
                </p>
                {success.next_run && (
                  <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-2)' }}>
                    First report arrives on{' '}
                    <span style={{ fontWeight: 500, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }}>
                      {new Date(success.next_run).toLocaleString()}
                    </span>.
                  </p>
                )}
              </div>
              <button
                onClick={onClose}
                className="fp-btn-accent"
                style={{ marginTop: 8, padding: '9px 24px' }}
              >
                Done
              </button>
            </div>
          ) : (
            <>
              {/* Email */}
              <div>
                <FormLabel>Email Address</FormLabel>
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="fp-input"
                />
              </div>

              {/* Frequency */}
              <div>
                <FormLabel>Frequency</FormLabel>
                <div style={{ display: 'flex', gap: 6 }}>
                  {['daily', 'weekly', 'monthly'].map(f => (
                    <button
                      key={f}
                      onClick={() => setFrequency(f)}
                      className={`fp-seg-btn ${frequency === f ? 'active' : ''}`}
                      style={{
                        flex: 1, textTransform: 'capitalize',
                        background: frequency === f ? 'var(--bg-hover)' : 'var(--bg-raised)',
                        border: `1px solid ${frequency === f ? 'var(--border-bright)' : 'var(--border-default)'}`,
                        borderRadius: 'var(--r-md)',
                        padding: '8px 4px',
                        cursor: 'pointer',
                        color: frequency === f ? 'var(--text-1)' : 'var(--text-2)',
                        fontSize: '13px', fontWeight: 500,
                        transition: 'all var(--t-fast) var(--ease)',
                        fontFamily: 'var(--font-body)',
                      }}
                    >
                      {f.charAt(0).toUpperCase() + f.slice(1)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Time */}
              <div>
                <FormLabel>Time (24h)</FormLabel>
                <div style={{ display: 'flex', gap: 8 }}>
                  <select
                    value={hour}
                    onChange={e => setHour(Number(e.target.value))}
                    className="fp-input"
                    style={{ fontFamily: 'var(--font-mono)' }}
                  >
                    {HOURS.map(h => (
                      <option key={h.value} value={h.value}>{h.label}:00</option>
                    ))}
                  </select>
                  <select
                    value={minute}
                    onChange={e => setMinute(Number(e.target.value))}
                    className="fp-input"
                    style={{ fontFamily: 'var(--font-mono)' }}
                  >
                    {MINUTES.map(m => (
                      <option key={m.value} value={m.value}>:{m.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Day of week (weekly only) */}
              {frequency === 'weekly' && (
                <div>
                  <FormLabel>Day of Week</FormLabel>
                  <select
                    value={dayOfWeek}
                    onChange={e => setDayOfWeek(e.target.value)}
                    className="fp-input"
                  >
                    {DAYS_OF_WEEK.map(d => (
                      <option key={d.value} value={d.value}>{d.label}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Day of month (monthly only) */}
              {frequency === 'monthly' && (
                <div>
                  <FormLabel>Day of Month</FormLabel>
                  <select
                    value={day}
                    onChange={e => setDay(Number(e.target.value))}
                    className="fp-input"
                  >
                    {DAYS_OF_MONTH.map(d => (
                      <option key={d.value} value={d.value}>{d.label}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* Preview */}
              {preview && (
                <div className="fp-preview-box">
                  {preview}
                </div>
              )}

              {/* Error */}
              {error && (
                <div style={{
                  background: 'var(--negative-dim)', border: '1px solid rgba(240,100,112,0.25)',
                  borderRadius: 'var(--r-md)', padding: '10px 14px',
                  fontSize: '13px', color: 'var(--negative)',
                }}>
                  {error}
                </div>
              )}

              {/* Submit */}
              <button
                onClick={handleSubmit}
                disabled={!email || submitting}
                className="fp-btn-accent"
                style={{ width: '100%', padding: '11px 24px' }}
              >
                {submitting ? (
                  <>
                    <svg className="fp-spinner" width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <circle cx="7" cy="7" r="5.5" stroke="rgba(4,8,16,0.3)" strokeWidth="1.5" />
                      <path d="M7 1.5a5.5 5.5 0 0 1 5.5 5.5" stroke="#040810" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    Scheduling…
                  </>
                ) : 'Schedule Report'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
