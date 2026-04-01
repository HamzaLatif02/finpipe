import { Download } from 'lucide-react'
import { getPdfUrl } from '../api/client'

export default function ReportDownload({ symbol, name, hasPdf }) {
  if (!hasPdf) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-5 py-4 text-sm text-slate-400">
        PDF report not available for {symbol}.
      </div>
    )
  }

  const filename = `${symbol}_report.pdf`

  return (
    <div className="rounded-xl border border-slate-200 bg-white px-5 py-5 flex flex-col sm:flex-row sm:items-center gap-4">
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-slate-900 truncate">{filename}</p>
        {name && <p className="text-sm text-slate-500 mt-0.5">{name}</p>}
        <p className="text-xs text-slate-400 mt-2">
          Generated from Yahoo Finance data. Not financial advice.
        </p>
      </div>
      <a
        href={getPdfUrl(symbol)}
        download={filename}
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 text-white
                   text-sm font-semibold hover:bg-blue-700 active:bg-blue-800
                   transition-colors shrink-0"
      >
        <Download size={16} />
        Download PDF
      </a>
    </div>
  )
}
