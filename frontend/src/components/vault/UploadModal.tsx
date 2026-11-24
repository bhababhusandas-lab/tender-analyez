import { useState, useRef } from 'react'
import { X, Upload, FileText, Loader2 } from 'lucide-react'
import { CATEGORIES, uploadDocument } from '../../api/documents'

interface UploadModalProps {
  onClose: () => void
  onUploaded: () => void
}

export function UploadModal({ onClose, onUploaded }: UploadModalProps) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState(CATEGORIES[0])
  const [expiryDate, setExpiryDate] = useState('')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    setFile(f)
    if (!name) setName(f.name.replace(/\.[^/.]+$/, ''))
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  const submit = async () => {
    if (!name.trim() || !file) { setError('Document name and file are required.'); return }
    setError('')
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('name', name.trim())
      fd.append('category', category)
      fd.append('expiry_date', expiryDate)
      fd.append('notes', notes)
      fd.append('file', file)
      await uploadDocument(fd)
      onUploaded()
      onClose()
    } catch {
      setError('Upload failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-panel rounded-2xl shadow-2xl w-full max-w-lg">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">Upload Document</h2>
          <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* File drop zone */}
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => fileRef.current?.click()}
            className="border-2 border-dashed border-gray-200 rounded-xl p-6 text-center cursor-pointer hover:border-gray-400 hover:bg-gray-50 transition-all"
          >
            {file ? (
              <div className="flex items-center justify-center gap-3">
                <FileText className="w-8 h-8 text-blue-500" />
                <div className="text-left">
                  <p className="font-medium text-gray-900 text-sm">{file.name}</p>
                  <p className="text-xs text-gray-400">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
              </div>
            ) : (
              <div>
                <Upload className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                <p className="text-sm text-gray-500">Drop file here or <span className="text-blue-600 font-medium">browse</span></p>
                <p className="text-xs text-gray-400 mt-1">PDF, JPG, PNG, XLSX, DOC — any format</p>
              </div>
            )}
            <input ref={fileRef} type="file" className="hidden" onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
          </div>

          {/* Document Name */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Document Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. ITR 2023-24, ISO Certificate, GST Return Q3"
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2.5 outline-none focus:border-gray-400 transition-colors"
            />
          </div>

          {/* Category + Expiry side by side */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Category *</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2.5 outline-none focus:border-gray-400 transition-colors bg-panel"
              >
                {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Expiry Date</label>
              <input
                type="date"
                value={expiryDate}
                onChange={(e) => setExpiryDate(e.target.value)}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2.5 outline-none focus:border-gray-400 transition-colors"
              />
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Notes (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Issued by ICAI, valid for 5 years..."
              rows={2}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2.5 outline-none focus:border-gray-400 transition-colors resize-none"
            />
          </div>

          {error && <p className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex gap-3 justify-end">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors">Cancel</button>
          <button
            onClick={submit}
            disabled={loading}
            className="px-5 py-2 text-sm font-medium bg-gray-900 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {loading ? 'Uploading…' : 'Upload Document'}
          </button>
        </div>
      </div>
    </div>
  )
}
