import { useState, useEffect, useCallback } from 'react'
import { Plus, FolderOpen, AlertTriangle, CheckCircle, XCircle, Search } from 'lucide-react'
import { fetchDocuments, fetchStats, deleteDocument, DocumentItem, VaultStats, CATEGORIES } from '../api/documents'
import { DocumentRow } from '../components/vault/DocumentRow'
import { UploadModal } from '../components/vault/UploadModal'

const ALL = 'All'
const FILTERS = [ALL, ...CATEGORIES]

export function DocumentVault() {
  const [docs, setDocs] = useState<DocumentItem[]>([])
  const [stats, setStats] = useState<VaultStats | null>(null)
  const [activeFilter, setActiveFilter] = useState(ALL)
  const [search, setSearch] = useState('')
  const [showUpload, setShowUpload] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    const [d, s] = await Promise.all([
      fetchDocuments(activeFilter === ALL ? '' : activeFilter),
      fetchStats(),
    ])
    setDocs(d)
    setStats(s)
    setLoading(false)
  }, [activeFilter])

  useEffect(() => { load() }, [load])

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this document?')) return
    await deleteDocument(id)
    load()
  }

  const filtered = docs.filter((d) =>
    search ? d.name.toLowerCase().includes(search.toLowerCase()) || d.original_filename.toLowerCase().includes(search.toLowerCase()) : true
  )

  const expiredDocs = filtered.filter((d) => d.expiry_status === 'expired')
  const expiringSoon = filtered.filter((d) => d.expiry_status === 'expiring-soon')
  const validDocs = filtered.filter((d) => d.expiry_status === 'valid')
  const noExpiry = filtered.filter((d) => d.expiry_status === 'no-expiry')

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Document Vault</h1>
          <p className="text-sm text-gray-500 mt-0.5">All certificates, licenses & compliance documents in one place</p>
        </div>
        <button
          onClick={() => setShowUpload(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-xl hover:bg-gray-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Upload Document
        </button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          <StatCard icon={<FolderOpen className="w-4 h-4" />} label="Total Documents" value={stats.total} color="blue" />
          <StatCard icon={<CheckCircle className="w-4 h-4" />} label="Valid" value={stats.valid} color="green" />
          <StatCard icon={<AlertTriangle className="w-4 h-4" />} label="Expiring Soon" value={stats.expiring_soon} color="amber" />
          <StatCard icon={<XCircle className="w-4 h-4" />} label="Expired" value={stats.expired} color="red" />
        </div>
      )}

      {/* Filters + Search */}
      <div className="flex flex-col sm:flex-row gap-3 mb-5">
        <div className="flex gap-2 flex-wrap">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setActiveFilter(f)}
              className={`text-xs font-medium px-3 py-1.5 rounded-full border transition-all ${
                activeFilter === f
                  ? 'bg-gray-900 text-white border-gray-900'
                  : 'bg-panel text-gray-600 border-gray-200 hover:border-gray-400'
              }`}
            >
              {f}
              {f !== ALL && stats?.categories[f] ? ` (${stats.categories[f]})` : ''}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 bg-panel border border-gray-200 rounded-lg px-3 py-2 ml-auto w-full sm:w-56">
          <Search className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search documents…"
            className="text-sm outline-none flex-1 bg-transparent placeholder-gray-400"
          />
        </div>
      </div>

      {/* Document List */}
      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <FolderOpen className="w-12 h-12 text-gray-200 mx-auto mb-3" />
          <p className="text-gray-400 text-sm">No documents yet.</p>
          <button onClick={() => setShowUpload(true)} className="mt-3 text-sm text-blue-600 hover:underline">Upload your first document</button>
        </div>
      ) : (
        <div className="space-y-5">
          {expiredDocs.length > 0 && (
            <Section title="Expired" count={expiredDocs.length} accent="text-red-600">
              {expiredDocs.map((d) => <DocumentRow key={d.id} doc={d} onDelete={handleDelete} />)}
            </Section>
          )}
          {expiringSoon.length > 0 && (
            <Section title="Expiring Soon (≤30 days)" count={expiringSoon.length} accent="text-amber-600">
              {expiringSoon.map((d) => <DocumentRow key={d.id} doc={d} onDelete={handleDelete} />)}
            </Section>
          )}
          {validDocs.length > 0 && (
            <Section title="Valid" count={validDocs.length} accent="text-green-600">
              {validDocs.map((d) => <DocumentRow key={d.id} doc={d} onDelete={handleDelete} />)}
            </Section>
          )}
          {noExpiry.length > 0 && (
            <Section title="No Expiry" count={noExpiry.length} accent="text-gray-500">
              {noExpiry.map((d) => <DocumentRow key={d.id} doc={d} onDelete={handleDelete} />)}
            </Section>
          )}
        </div>
      )}

      {showUpload && <UploadModal onClose={() => setShowUpload(false)} onUploaded={load} />}
    </div>
  )
}

function StatCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: number; color: string }) {
  const colors: Record<string, string> = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    amber: 'bg-amber-50 text-amber-600',
    red: 'bg-red-50 text-red-600',
  }
  return (
    <div className="bg-panel border border-gray-100 rounded-xl p-4 shadow-sm">
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-3 ${colors[color]}`}>{icon}</div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
    </div>
  )
}

function Section({ title, count, accent, children }: { title: string; count: number; accent: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <p className={`text-xs font-semibold uppercase tracking-wide ${accent}`}>{title}</p>
        <span className="text-xs text-gray-400">({count})</span>
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  )
}
