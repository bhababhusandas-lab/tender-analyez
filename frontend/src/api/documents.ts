import { api, apiUrl } from './client'

export interface DocumentItem {
  id: number
  name: string
  category: string
  original_filename: string
  file_size: number
  mime_type: string
  expiry_date: string | null
  expiry_status: 'valid' | 'expiring-soon' | 'expired' | 'no-expiry'
  notes: string | null
  uploaded_at: string
}

export interface VaultStats {
  total: number
  expired: number
  expiring_soon: number
  valid: number
  categories: Record<string, number>
}

export const CATEGORIES = [
  'Financial',
  'Legal & Registration',
  'Technical Credentials',
  'HR & Compliance',
  'Digital Signature (DSC)',
  'Other',
]

export async function fetchDocuments(category = ''): Promise<DocumentItem[]> {
  const res = await api.get('/api/v1/documents', { params: category ? { category } : {} })
  return res.data
}

export async function fetchStats(): Promise<VaultStats> {
  const res = await api.get('/api/v1/documents/stats')
  return res.data
}

export async function uploadDocument(formData: FormData): Promise<DocumentItem> {
  const res = await api.post('/api/v1/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function deleteDocument(id: number): Promise<void> {
  await api.delete(`/api/v1/documents/${id}`)
}

export function downloadUrl(id: number): string {
  return apiUrl(`/api/v1/documents/${id}/download`)
}

/** Auth-aware document download. */
export async function downloadDocument(id: number, filename: string): Promise<void> {
  const res = await api.get(`/api/v1/documents/${id}/download`, { responseType: 'blob' })
  const url = window.URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}
