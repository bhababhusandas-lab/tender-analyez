import { api } from './client'

export type RunKind = 'pipeline' | 'roadmap'

export interface TenderListItem {
  id: number; name: string; reference_no: string
  latest_decision: string; latest_deadline: string; version_count: number
  last_activity_at: string | null; unread: boolean; running: boolean
  latest_kind: RunKind; latest_job_id: string | null; bid_id: number | null
}

export interface TenderChange { field: 'decision' | 'quote' | 'deadline'; before: string; after: string }

export interface TenderVersionInfo {
  id: number; number: number | null; label: string; kind: RunKind
  status: 'running' | 'completed' | 'review_required' | 'stopped' | 'failed'
  note: string; decision: string; quote: string; deadline: string; job_id: string | null
  created_at: string | null; completed_at: string | null; changes: TenderChange[]
}

export interface TenderDocumentInfo {
  id: number; filename: string; size: number; mime_type: string
  version_id: number; version_number: number | null; uploaded_at: string | null
}

export interface TenderDetail extends TenderListItem {
  versions: TenderVersionInfo[]; documents: TenderDocumentInfo[]
}

/** Fired after anything that changes the history list, so the sidebar refreshes. */
export const HISTORY_CHANGED = 'taa:history-changed'
export const notifyHistoryChanged = () => window.dispatchEvent(new Event(HISTORY_CHANGED))

export const fetchTenders = async (q = '', limit = 20): Promise<TenderListItem[]> =>
  (await api.get('/api/v1/tender-history', { params: { q, limit } })).data.items

export const fetchTender = async (id: number): Promise<TenderDetail> =>
  (await api.get(`/api/v1/tender-history/${id}`)).data

export const markTenderViewed = async (id: number): Promise<void> => {
  await api.post(`/api/v1/tender-history/${id}/viewed`)
}

export const renameTender = async (id: number, name: string): Promise<void> => {
  await api.patch(`/api/v1/tender-history/${id}`, { name })
}

export const deleteTender = async (id: number): Promise<void> => {
  await api.delete(`/api/v1/tender-history/${id}`)
}

export const reanalyzeTender = async (id: number, kind: RunKind, note: string, files: File[]):
  Promise<{ tender_id: number; job_id: string; kind: RunKind; version_id: number }> => {
  const fd = new FormData()
  fd.append('kind', kind)
  fd.append('note', note)
  files.forEach(f => fd.append('files', f))
  return (await api.post(`/api/v1/tender-history/${id}/reanalyze`, fd)).data
}

async function saveBlob(path: string, filename: string, params?: Record<string, unknown>) {
  const res = await api.get(path, { responseType: 'blob', params })
  const url = window.URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}

export const downloadTenderDocument = (tenderId: number, doc: TenderDocumentInfo) =>
  saveBlob(`/api/v1/tender-history/${tenderId}/documents/${doc.id}`, doc.filename)

export const downloadVersionPdf = (tenderId: number, number: number, full = false) =>
  saveBlob(`/api/v1/tender-history/${tenderId}/versions/${number}/export`, `Tender_${tenderId}_v${number}${full ? '_Full' : ''}.pdf`,
    full ? { full: true } : undefined)

/** URL that reopens a run on the matching analysis screen. */
export const runUrl = (tenderId: number, kind: RunKind, jobId: string | null) =>
  `/app/${kind === 'roadmap' ? 'analysis' : 'bid'}?tender=${tenderId}${jobId ? `&job=${jobId}` : ''}`
