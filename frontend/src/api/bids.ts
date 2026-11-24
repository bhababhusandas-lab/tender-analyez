import { api, apiUrl } from './client'

export interface Bid {
  id: number; tender_name: string; reference_no: string; portal: string; department: string
  estimated_value: string; emd_amount: string; submission_deadline: string
  recommended_quote: string; bid_confidence: string; status: string
  pipeline_result: string; tender_text: string; notes: string
  created_at: string; updated_at: string
}

export interface BidStats { total: number; draft: number; submitted: number; won: number; lost: number; withdrawn: number }

export const STATUS_COLORS: Record<string, string> = {
  draft:      'bg-gray-100 text-gray-600',
  submitted:  'bg-blue-100 text-blue-700',
  won:        'bg-green-100 text-green-700',
  lost:       'bg-red-100 text-red-700',
  withdrawn:  'bg-amber-100 text-amber-700',
}

export const fetchBids = async (status = ''): Promise<Bid[]> =>
  (await api.get('/api/v1/bids', { params: status ? { status } : {} })).data

export const fetchBidStats = async (): Promise<BidStats> =>
  (await api.get('/api/v1/bids/stats/summary')).data

export const createBid = async (data: Partial<Bid> & { tender_id?: number }): Promise<Bid> =>
  (await api.post('/api/v1/bids', data)).data

export const updateBidStatus = async (id: number, status: string, notes = ''): Promise<Bid> =>
  (await api.patch(`/api/v1/bids/${id}/status`, { status, notes })).data

export const deleteBid = async (id: number): Promise<void> =>
  api.delete(`/api/v1/bids/${id}`)

export const exportUrl = (id: number, full = false) => apiUrl(`/api/v1/bids/${id}/export${full ? '?full=true' : ''}`)

/** Auth-aware PDF download: fetches as blob then triggers browser download.
 *  Default is the 1–2 page summary; `full` appends every specialist's report. */
export async function downloadBidPdf(id: number, suggestedName = `Bid_${id}.pdf`, full = false): Promise<void> {
  const res = await api.get(`/api/v1/bids/${id}/export`, { responseType: 'blob', params: full ? { full: true } : undefined })
  const url = window.URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url; a.download = suggestedName
  document.body.appendChild(a); a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}
