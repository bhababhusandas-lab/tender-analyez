import { api } from './client'

export interface PastBid {
  id: number; title: string; department: string; contract_value: string
  year_won: string; outcome: string; original_filename: string
  text_length: number; uploaded_at: string
}

export const fetchPastBids = async (): Promise<PastBid[]> =>
  (await api.get('/api/v1/past-bids')).data

export const uploadPastBid = async (fd: FormData): Promise<PastBid> =>
  (await api.post('/api/v1/past-bids/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })).data

export const deletePastBid = async (id: number): Promise<void> =>
  api.delete(`/api/v1/past-bids/${id}`)
