import { useState, useEffect } from 'react'

function RateLimitError({ retryAfter }) {
  const [secondsLeft, setSecondsLeft] = useState(retryAfter || null)

  useEffect(() => {
    if (!retryAfter) return
    setSecondsLeft(retryAfter)
    const timer = setInterval(() => {
      setSecondsLeft(s => {
        if (s <= 1) { clearInterval(timer); return 0 }
        return s - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [retryAfter])

  const mins = secondsLeft !== null ? Math.floor(secondsLeft / 60) : null
  const secs = secondsLeft !== null ? secondsLeft % 60 : null

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '60vh',
    }}>
      <div className="fp-card" style={{
        padding: '48px 40px', maxWidth: '420px', width: '100%',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20,
        textAlign: 'center',
      }}>
        <div style={{
          width: 52, height: 52, borderRadius: '50%',
          background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '22px',
        }}>
          &#9203;
        </div>
        <div>
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 700,
            fontSize: '16px', color: 'var(--text-1)', marginBottom: 8,
          }}>
            Rate Limit Reached
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-2)', lineHeight: 1.6 }}>
            You've sent too many requests in a short time.
            {secondsLeft !== null && secondsLeft > 0 && (
              <> Please wait before trying again.</>
            )}
          </div>
        </div>
        {secondsLeft !== null && secondsLeft > 0 && (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: '28px', fontWeight: 700,
            color: '#F59E0B', letterSpacing: '0.05em',
          }}>
            {mins > 0 ? `${mins}:${String(secs).padStart(2, '0')}` : `${secs}s`}
          </div>
        )}
        {(secondsLeft === null || secondsLeft === 0) && (
          <div style={{ fontSize: '12px', color: 'var(--text-3)' }}>
            You can try again now.
          </div>
        )}
      </div>
    </div>
  )
}

export default function ProgressOverlay({
  message,
  percent = 0,
  usingFallback = false,
  title = 'Analysing...',
  subtitle = null,
  rateLimitError = false,
  rateLimitRetryAfter = null,
}) {
  if (rateLimitError) {
    return <RateLimitError retryAfter={rateLimitRetryAfter} />
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '60vh',
      animation: 'fp-fade-in var(--t-base) var(--ease)',
    }}>
      <div className="fp-card" style={{
        padding: '48px 40px', maxWidth: '420px', width: '100%',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 28,
        textAlign: 'center',
      }}>

        {/* Spinner ring */}
        <div style={{ position: 'relative', width: 60, height: 60 }}>
          <svg width="60" height="60" viewBox="0 0 60 60" fill="none" style={{ position: 'absolute', inset: 0 }}>
            <circle cx="30" cy="30" r="26" stroke="var(--border-default)" strokeWidth="2" />
          </svg>
          <svg width="60" height="60" viewBox="0 0 60 60" fill="none" className="fp-spinner" style={{ position: 'absolute', inset: 0 }}>
            <path d="M30 4 A 26 26 0 0 1 56 30" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" fill="none" />
          </svg>
          {/* Percentage label */}
          <div style={{
            position: 'absolute', inset: 0, display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            fontFamily: 'var(--font-mono)', fontSize: '11px',
            fontWeight: 600, color: 'var(--text-2)',
          }}>
            {percent > 0 ? `${percent}%` : ''}
          </div>
        </div>

        {/* Text block */}
        <div style={{ width: '100%' }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontWeight: 700,
            fontSize: '16px', color: 'var(--text-1)', marginBottom: 6,
          }}>
            {title}
          </div>
          {subtitle && (
            <div style={{ fontSize: '12px', color: 'var(--text-3)', marginBottom: 8 }}>
              {subtitle}
            </div>
          )}
          <div style={{
            fontSize: '13px', color: 'var(--text-2)',
            minHeight: '20px',
            transition: 'opacity var(--t-base) var(--ease)',
          }}>
            {message || ' '}
          </div>
        </div>

        {/* Progress bar */}
        <div style={{ width: '100%' }}>
          <div style={{
            width: '100%', height: 4,
            background: 'var(--border-default)',
            borderRadius: 4,
            overflow: 'hidden',
          }}>
            <div style={{
              height: '100%',
              width: `${percent}%`,
              background: 'var(--accent)',
              borderRadius: 4,
              transition: 'width 0.6s ease-in-out',
            }} />
          </div>
          <div style={{
            display: 'flex', justifyContent: 'flex-end',
            marginTop: 5, fontSize: '11px',
            color: 'var(--text-4)',
          }}>
            {usingFallback
              ? <span style={{ fontStyle: 'italic', color: 'var(--text-4)' }}>Estimated progress</span>
              : <span style={{ color: 'var(--positive)', fontWeight: 600 }}>&#9679; Live progress</span>
            }
          </div>
        </div>

      </div>
    </div>
  )
}
