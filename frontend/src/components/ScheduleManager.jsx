import { useEffect, useState, useRef } from 'react'
import { X, CalendarCheck, Trash2, Send, Clock, RefreshCw } from 'lucide-react'
import { getSchedules, removeSchedule, sendNow, getPendingSchedules, resendConfirmation } from '../api/client'
import { hasAnyTokens } from '../utils/tokenStore'

export default function ScheduleManager({ onClose }) {
  const [jobs,         setJobs]         = useState(null)
  const [pendingJobs,  setPendingJobs]  = useState([])
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState(null)
  const [removing,     setRemoving]     = useState(null)
  const [sending,      setSending]      = useState(null)
  const [resending,    setResending]    = useState(null)   // job_id being resent
  const [rowErrors,    setRowErrors]    = useState({})
  const [rowMessages,  setRowMessages]  = useState({})
  const dismissTimers = useRef({})

  function load() {
    if (!hasAnyTokens()) {
      setLoading(false)
      setJobs([])
      setPendingJobs([])
      return
    }
    setLoading(true)
    setError(null)
    Promise.all([getSchedules(), getPendingSchedules()])
      .then(([confirmed, pending]) => {
        setJobs(confirmed)
        setPendingJobs(pending)
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  async function handleRemove(job) {
    if (!window.confirm(`Cancel the scheduled report for ${job.symbol}? This cannot be undone.`)) return
    setRemoving(job.job_id)
    setRowErrors(prev => { const next = { ...prev }; delete next[job.job_id]; return next })
    try {
      await removeSchedule(job.job_id)
      setJobs(prev => prev.filter(j => j.job_id !== job.job_id))
    } catch (err) {
      setRowErrors(prev => ({ ...prev, [job.job_id]: err.message }))
    } finally {
      setRemoving(null)
    }
  }

  async function handleSendNow(job) {
    if (!window.confirm(`Send an immediate report for ${job.symbol} to ${job.email}?`)) return
    setSending(job.job_id)
    setRowErrors(prev  => { const n = { ...prev };  delete n[job.job_id]; return n })
    setRowMessages(prev => { const n = { ...prev }; delete n[job.job_id]; return n })
    try {
      const res = await sendNow(job.job_id)
      // The endpoint returns immediately (queued) — the email arrives ~1–2 min later
      const msg = res.message || `Report queued — email will arrive at ${job.email} shortly`
      setRowMessages(prev => ({ ...prev, [job.job_id]: msg }))
      // Auto-dismiss after 10 s (longer than "sent" since the email is still in flight)
      clearTimeout(dismissTimers.current[job.job_id])
      dismissTimers.current[job.job_id] = setTimeout(() => {
        setRowMessages(prev => { const n = { ...prev }; delete n[job.job_id]; return n })
      }, 10000)
    } catch (err) {
      setRowErrors(prev => ({ ...prev, [job.job_id]: err.message }))
    } finally {
      setSending(null)
    }
  }

  async function handleResend(job) {
    setResending(job.job_id)
    setRowErrors(prev  => { const n = { ...prev };  delete n[job.job_id]; return n })
    setRowMessages(prev => { const n = { ...prev }; delete n[job.job_id]; return n })
    try {
      await resendConfirmation(job.job_id)
      setRowMessages(prev => ({ ...prev, [job.job_id]: `Confirmation resent to ${job.email}` }))
      clearTimeout(dismissTimers.current[job.job_id])
      dismissTimers.current[job.job_id] = setTimeout(() => {
        setRowMessages(prev => { const n = { ...prev }; delete n[job.job_id]; return n })
      }, 8000)
    } catch (err) {
      setRowErrors(prev => ({ ...prev, [job.job_id]: err.message }))
    } finally {
      setResending(null)
    }
  }

  function fmtFrequency(job) {
    if (job.frequency === 'daily')   return 'Daily'
    if (job.frequency === 'weekly')  return 'Weekly'
    if (job.frequency === 'monthly') return 'Monthly'
    return job.frequency
  }

  // Determine which empty-state message to show
  const noLocalTokens = !hasAnyTokens()

  return (
    <div
      className="fp-drawer-backdrop"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="fp-drawer-panel">

        {/* ── Header ─────────────────────────────────────────────────── */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '20px 28px',
          borderBottom: '1px solid var(--border-subtle)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 'var(--r-md)',
              background: 'var(--accent-dim)', border: '1px solid rgba(79,172,247,0.22)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <CalendarCheck size={16} color="var(--accent)" />
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '16px', color: 'var(--text-1)' }}>
                Scheduled Reports
              </div>
              <div style={{ fontSize: '12px', color: 'var(--text-3)', marginTop: 1 }}>
                Manage automated report delivery
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: 8,
              color: 'var(--text-3)', borderRadius: 'var(--r-md)',
              lineHeight: 1, transition: 'all var(--t-fast) var(--ease)',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = 'var(--bg-hover)'
              e.currentTarget.style.color = 'var(--text-1)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'none'
              e.currentTarget.style.color = 'var(--text-3)'
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* ── Body ───────────────────────────────────────────────────── */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '16px 28px' }}>

          {loading && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '64px 0', gap: 10, color: 'var(--text-3)',
            }}>
              <svg className="fp-spinner" width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="7" stroke="var(--border-bright)" strokeWidth="1.5" />
                <path d="M9 2a7 7 0 0 1 7 7" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <span style={{ fontSize: '13px' }}>Loading schedules…</span>
            </div>
          )}

          {error && (
            <div style={{ padding: '32px 0', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'center' }}>
              <p style={{ fontSize: '13px', color: 'var(--negative)', margin: 0 }}>{error}</p>
              <button className="fp-btn-ghost" onClick={load} style={{ padding: '7px 16px' }}>
                Retry
              </button>
            </div>
          )}

          {!loading && !error && jobs?.length === 0 && (
            <div style={{ padding: '64px 0', textAlign: 'center' }}>
              <div style={{ marginBottom: 12 }}>
                <CalendarCheck size={32} color="var(--text-4)" style={{ margin: '0 auto' }} />
              </div>
              {noLocalTokens ? (
                <>
                  <p style={{ fontSize: '14px', color: 'var(--text-2)', margin: '0 0 6px', fontWeight: 500 }}>
                    No scheduled reports found in this browser
                  </p>
                  <p style={{ fontSize: '13px', color: 'var(--text-3)', margin: 0, maxWidth: 320, marginLeft: 'auto', marginRight: 'auto' }}>
                    Scheduled reports are linked to the browser where they were created.
                  </p>
                </>
              ) : (
                <>
                  <p style={{ fontSize: '14px', color: 'var(--text-2)', margin: '0 0 6px', fontWeight: 500 }}>
                    No scheduled reports yet
                  </p>
                  <p style={{ fontSize: '13px', color: 'var(--text-3)', margin: 0 }}>
                    Run an analysis and click <span style={{ color: 'var(--text-2)', fontWeight: 500 }}>Schedule Report</span> to set one up.
                  </p>
                </>
              )}
            </div>
          )}

          {jobs?.length > 0 && (
            <>
              {/* ── Desktop table ─────────────────────────────────────── */}
              <div className="fp-sched-table-wrap">
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <th style={{ textAlign: 'left', padding: '8px 12px 10px 0', fontSize: '10px', fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-3)', fontFamily: 'var(--font-body)' }}>Asset</th>
                      <th style={{ textAlign: 'left', padding: '8px 12px 10px', fontSize: '10px', fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-3)', fontFamily: 'var(--font-body)' }}>Frequency</th>
                      <th style={{ textAlign: 'left', padding: '8px 12px 10px', fontSize: '10px', fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-3)', fontFamily: 'var(--font-body)' }}>Next Report</th>
                      <th style={{ textAlign: 'left', padding: '8px 12px 10px', fontSize: '10px', fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-3)', fontFamily: 'var(--font-body)' }}>Email</th>
                      <th style={{ padding: '8px 0 10px' }} />
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map(job => (
                      <tr
                        key={job.job_id}
                        className="fp-table-row"
                        style={{ borderBottom: '1px solid var(--border-subtle)' }}
                      >
                        <td style={{ padding: '12px 12px 12px 0' }}>
                          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, fontSize: '13px', color: 'var(--text-1)' }}>
                            {job.symbol}
                          </span>
                          {job.name && job.name !== job.symbol && (
                            <span style={{ display: 'block', fontSize: '11px', color: 'var(--text-3)', marginTop: 2 }}>
                              {job.name}
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '12px' }}>
                          <span className="fp-badge fp-badge-neutral" style={{ fontSize: '10px' }}>
                            {fmtFrequency(job)}
                          </span>
                        </td>
                        <td style={{ padding: '12px', fontSize: '12px', color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>
                          {job.next_run_time
                            ? new Date(job.next_run_time.replace(' ', 'T')).toLocaleString()
                            : <span style={{ color: 'var(--text-4)' }}>—</span>
                          }
                        </td>
                        <td style={{ padding: '12px', maxWidth: 180 }}>
                          <span style={{ fontSize: '12px', color: 'var(--text-3)', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {job.email}
                          </span>
                        </td>
                        <td style={{ padding: '12px 0', textAlign: 'right' }}>
                          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                            <button
                              onClick={() => handleSendNow(job)}
                              disabled={sending === job.job_id || removing === job.job_id}
                              className="fp-send-btn"
                              title="Send report now"
                            >
                              {sending === job.job_id ? (
                                <svg className="fp-spinner" width="12" height="12" viewBox="0 0 12 12" fill="none">
                                  <circle cx="6" cy="6" r="4.5" stroke="var(--border-bright)" strokeWidth="1.5" />
                                  <path d="M6 1.5a4.5 4.5 0 0 1 4.5 4.5" stroke="var(--positive)" strokeWidth="1.5" strokeLinecap="round" />
                                </svg>
                              ) : <Send size={12} />}
                              Send now
                            </button>
                            <button
                              onClick={() => handleRemove(job)}
                              disabled={removing === job.job_id || sending === job.job_id}
                              className="fp-cancel-btn"
                            >
                              {removing === job.job_id ? (
                                <svg className="fp-spinner" width="12" height="12" viewBox="0 0 12 12" fill="none">
                                  <circle cx="6" cy="6" r="4.5" stroke="var(--border-bright)" strokeWidth="1.5" />
                                  <path d="M6 1.5a4.5 4.5 0 0 1 4.5 4.5" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
                                </svg>
                              ) : <Trash2 size={12} />}
                              Cancel
                            </button>
                          </div>
                          {rowMessages[job.job_id] && (
                            <div style={{ fontSize: '11px', color: 'var(--positive)', marginTop: 5, textAlign: 'right', lineHeight: 1.4 }}>
                              {rowMessages[job.job_id]}
                            </div>
                          )}
                          {rowErrors[job.job_id] && (
                            <div style={{ fontSize: '11px', color: 'var(--negative)', marginTop: 5, maxWidth: 200, textAlign: 'right', lineHeight: 1.4 }}>
                              {rowErrors[job.job_id]}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* ── Mobile cards ──────────────────────────────────────── */}
              <div className="fp-sched-cards" style={{ flexDirection: 'column', gap: 10, display: 'none' }}>
                {jobs.map(job => (
                  <div key={job.job_id} style={{
                    background: 'var(--bg-raised)', border: '1px solid var(--border-default)',
                    borderRadius: 'var(--r-lg)', padding: '14px 16px',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 10 }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, fontSize: '14px', color: 'var(--text-1)' }}>
                            {job.symbol}
                          </span>
                          <span className="fp-badge fp-badge-neutral" style={{ fontSize: '10px' }}>
                            {fmtFrequency(job)}
                          </span>
                        </div>
                        {job.name && job.name !== job.symbol && (
                          <span style={{ fontSize: '12px', color: 'var(--text-3)', display: 'block', marginTop: 2 }}>
                            {job.name}
                          </span>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12 }}>
                      <div style={{ fontSize: '12px', color: 'var(--text-3)' }}>
                        <span style={{ color: 'var(--text-4)', marginRight: 6 }}>Email</span>
                        <span style={{ color: 'var(--text-2)' }}>{job.email}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                        <span style={{ color: 'var(--text-4)', marginRight: 6, fontFamily: 'var(--font-body)' }}>Next</span>
                        {job.next_run_time
                          ? new Date(job.next_run_time.replace(' ', 'T')).toLocaleString()
                          : '—'
                        }
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        onClick={() => handleSendNow(job)}
                        disabled={sending === job.job_id || removing === job.job_id}
                        className="fp-send-btn"
                        style={{ flex: 1, justifyContent: 'center', padding: '10px 8px' }}
                      >
                        {sending === job.job_id ? (
                          <svg className="fp-spinner" width="12" height="12" viewBox="0 0 12 12" fill="none">
                            <circle cx="6" cy="6" r="4.5" stroke="var(--border-bright)" strokeWidth="1.5" />
                            <path d="M6 1.5a4.5 4.5 0 0 1 4.5 4.5" stroke="var(--positive)" strokeWidth="1.5" strokeLinecap="round" />
                          </svg>
                        ) : <Send size={12} />}
                        Send now
                      </button>
                      <button
                        onClick={() => handleRemove(job)}
                        disabled={removing === job.job_id || sending === job.job_id}
                        className="fp-cancel-btn"
                        style={{ flex: 1, justifyContent: 'center', padding: '10px 8px' }}
                      >
                        {removing === job.job_id ? (
                          <svg className="fp-spinner" width="12" height="12" viewBox="0 0 12 12" fill="none">
                            <circle cx="6" cy="6" r="4.5" stroke="var(--border-bright)" strokeWidth="1.5" />
                            <path d="M6 1.5a4.5 4.5 0 0 1 4.5 4.5" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
                          </svg>
                        ) : <Trash2 size={12} />}
                        Cancel
                      </button>
                    </div>
                    {rowMessages[job.job_id] && (
                      <div style={{ fontSize: '11px', color: 'var(--positive)', marginTop: 8, lineHeight: 1.4 }}>
                        {rowMessages[job.job_id]}
                      </div>
                    )}
                    {rowErrors[job.job_id] && (
                      <div style={{ fontSize: '11px', color: 'var(--negative)', marginTop: 8, lineHeight: 1.4 }}>
                        {rowErrors[job.job_id]}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
          {/* ── Pending / awaiting confirmation ─────────────────────── */}
          {pendingJobs.length > 0 && (
            <div style={{ marginTop: jobs?.length > 0 ? 24 : 0 }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
              }}>
                <Clock size={13} color="var(--text-3)" />
                <span style={{ fontSize: '11px', fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-3)', fontFamily: 'var(--font-body)' }}>
                  Awaiting Confirmation
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {pendingJobs.map(job => (
                  <div key={job.job_id} style={{
                    background: 'var(--bg-raised)', border: '1px solid var(--border-default)',
                    borderRadius: 'var(--r-md)', padding: '12px 14px',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, fontSize: '13px', color: 'var(--text-1)' }}>
                            {job.symbol}
                          </span>
                          <span className="fp-badge fp-badge-neutral" style={{ fontSize: '10px' }}>
                            {job.frequency}
                          </span>
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-3)', marginTop: 3 }}>
                          {String(job.hour).padStart(2, '0')}:{String(job.minute).padStart(2, '0')} London · {job.email}
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-3)', marginTop: 2 }}>
                          Check your inbox and click the link to activate.
                        </div>
                      </div>
                      <button
                        onClick={() => handleResend(job)}
                        disabled={resending === job.job_id}
                        className="fp-btn-ghost"
                        style={{ padding: '6px 12px', fontSize: '12px', display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0 }}
                        title="Resend confirmation email"
                      >
                        {resending === job.job_id ? (
                          <svg className="fp-spinner" width="12" height="12" viewBox="0 0 12 12" fill="none">
                            <circle cx="6" cy="6" r="4.5" stroke="var(--border-bright)" strokeWidth="1.5" />
                            <path d="M6 1.5a4.5 4.5 0 0 1 4.5 4.5" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
                          </svg>
                        ) : (
                          <RefreshCw size={11} />
                        )}
                        Resend
                      </button>
                    </div>
                    {rowMessages[job.job_id] && (
                      <div style={{ fontSize: '11px', color: 'var(--positive)', marginTop: 6 }}>
                        {rowMessages[job.job_id]}
                      </div>
                    )}
                    {rowErrors[job.job_id] && (
                      <div style={{ fontSize: '11px', color: 'var(--negative)', marginTop: 6 }}>
                        {rowErrors[job.job_id]}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
