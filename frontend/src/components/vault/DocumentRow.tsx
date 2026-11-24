import { Download, Trash2, FileText, FileSpreadsheet, Image, File } from 'lucide-react'
import { DocumentItem, downloadUrl } from '../../api/documents'

interface DocumentRowProps {
  doc: DocumentItem
  onDelete: (id: number) => void
}

function FileIcon({ mime }: { mime: string }) {
  const cls = 'w-4 h-4'
  if (mime.includes('pdf')) return <FileText className={`${cls} text-red-500`} />
  if (mime.includes('spreadsheet') || mime.includes('excel') || mime.includes('csv')) return <FileSpreadsheet className={`${cls} text-green-600`} />
  if (mime.includes('image')) return <Image className={`${cls} text-blue-500`} />
  return <File className={`${cls} text-gray-400`} />
}

const STATUS_STYLES = {
  valid: 'bg-green-100 text-green-700',
  'expiring-soon': 'bg-amber-100 text-amber-700',
  expired: 'bg-red-100 text-red-700',
  'no-expiry': 'bg-gray-100 text-gray-500',
}

const STATUS_LABELS = {
  valid: 'Valid',
  'expiring-soon': 'Expiring soon',
  expired: 'Expired',
  'no-expiry': 'No expiry',
}

const CATEGORY_COLORS: Record<string, string> = {
  'Financial': 'bg-blue-50 text-blue-700',
  'Legal & Registration': 'bg-slate-100 text-slate-700',
  'Technical Credentials': 'bg-emerald-50 text-emerald-700',
  'HR & Compliance': 'bg-green-50 text-green-700',
  'Digital Signature (DSC)': 'bg-pink-50 text-pink-700',
  'Other': 'bg-gray-100 text-gray-600',
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function DocumentRow({ doc, onDelete }: DocumentRowProps) {
  const daysLeft = doc.expiry_date
    ? Math.ceil((new Date(doc.expiry_date).getTime() - Date.now()) / 86400000)
    : null

  return (
    <div className="flex items-center gap-4 px-4 py-3.5 bg-panel border border-gray-100 rounded-xl hover:border-gray-200 hover:shadow-sm transition-all group">
      {/* File icon */}
      <div className="w-9 h-9 bg-gray-50 rounded-lg flex items-center justify-center flex-shrink-0 border border-gray-100">
        <FileIcon mime={doc.mime_type} />
      </div>

      {/* Name + filename */}
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm text-gray-900 truncate">{doc.name}</p>
        <p className="text-xs text-gray-400 truncate">{doc.original_filename} · {formatBytes(doc.file_size)}</p>
      </div>

      {/* Category */}
      <span className={`text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap hidden sm:inline-flex ${CATEGORY_COLORS[doc.category] || 'bg-gray-100 text-gray-600'}`}>
        {doc.category}
      </span>

      {/* Expiry */}
      <div className="text-right hidden md:block w-32 flex-shrink-0">
        {doc.expiry_date ? (
          <>
            <p className="text-xs text-gray-500">{formatDate(doc.expiry_date)}</p>
            <p className={`text-xs font-medium mt-0.5 ${daysLeft !== null && daysLeft < 0 ? 'text-red-600' : daysLeft !== null && daysLeft <= 30 ? 'text-amber-600' : 'text-green-600'}`}>
              {daysLeft !== null && daysLeft < 0 ? `${Math.abs(daysLeft)}d overdue` : daysLeft !== null && daysLeft === 0 ? 'Expires today' : daysLeft !== null ? `${daysLeft}d left` : ''}
            </p>
          </>
        ) : (
          <p className="text-xs text-gray-400">No expiry</p>
        )}
      </div>

      {/* Status badge */}
      <span className={`text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap flex-shrink-0 ${STATUS_STYLES[doc.expiry_status]}`}>
        {STATUS_LABELS[doc.expiry_status]}
      </span>

      {/* Actions */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
        <a
          href={downloadUrl(doc.id)}
          download={doc.original_filename}
          className="w-8 h-8 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-700 transition-colors"
          title="Download"
        >
          <Download className="w-3.5 h-3.5" />
        </a>
        <button
          onClick={() => onDelete(doc.id)}
          className="w-8 h-8 rounded-lg hover:bg-red-50 flex items-center justify-center text-gray-400 hover:text-red-600 transition-colors"
          title="Delete"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}
