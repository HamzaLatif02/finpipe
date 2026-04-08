import { Download, Eye, FileText } from 'lucide-react'
import { getPdfUrl, getViewUrl } from '../api/client'

export default function ReportDownload({ symbol, name, hasPdf }) {
  if (!hasPdf) {
    return (
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border-default)',
        borderRadius: 'var(--r-lg)', padding: '14px 18px',
        fontSize: '13px', color: 'var(--text-3)',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <FileText size={14} color="var(--text-4)" />
        PDF report not yet available for {symbol}.
      </div>
    )
  }

  const filename = `${symbol}_report.pdf`

  return (
    <div className="fp-card fp-report-row" style={{
      padding: '20px 24px',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 20, flexWrap: 'wrap',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        {/* File icon */}
        <div style={{
          width: 40, height: 40, borderRadius: 'var(--r-md)',
          background: 'var(--bg-raised)', border: '1px solid var(--border-default)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <FileText size={18} color="var(--accent)" />
        </div>
        <div>
          <div style={{
            fontFamily: 'var(--font-mono)', fontWeight: 500,
            fontSize: '13px', color: 'var(--text-1)',
          }}>
            {filename}
          </div>
          {name && (
            <div style={{ fontSize: '12px', color: 'var(--text-3)', marginTop: 2 }}>
              {name}
            </div>
          )}
          <div style={{ fontSize: '11px', color: 'var(--text-4)', marginTop: 4 }}>
            Generated from Yahoo Finance data · Not financial advice
          </div>
        </div>
      </div>

      <div className="fp-report-btns" style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
        <a
          href={getViewUrl(symbol)}
          target="_blank"
          rel="noopener noreferrer"
          className="fp-btn-primary"
          style={{ padding: '10px 18px', textDecoration: 'none' }}
        >
          <Eye size={15} />
          View
        </a>
        <a
          href={getPdfUrl(symbol)}
          download={filename}
          className="fp-btn-accent"
          style={{ padding: '10px 18px', textDecoration: 'none' }}
        >
          <Download size={15} />
          Download
        </a>
      </div>
    </div>
  )
}
