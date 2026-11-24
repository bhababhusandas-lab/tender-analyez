import { api } from './client'

export interface UsageSnapshot {
  plan: 'free' | 'starter' | 'growth' | 'professional' | 'enterprise' | string
  limits: {
    total: number | null
    daily: number | null
    monthly: number | null
    pipeline_monthly: number | null
    roadmap_monthly: number | null
    vault_documents: number | null
  }
  used_total: number
  used_24h: number
  used_30d: number
  pipeline_used_30d: number
  roadmap_used_30d: number
}

export interface UsageLimitInfo {
  code: 'USAGE_LIMIT_EXCEEDED'
  limit_type: 'total' | 'daily' | 'monthly'
  plan: string
  used: number
  limit: number
  kind?: 'pipeline' | 'roadmap'
  message: string
  resets_at?: string
}

export const fetchUsage = async (): Promise<UsageSnapshot> =>
  (await api.get('/api/v1/usage')).data

/** Detects the 402 USAGE_LIMIT_EXCEEDED error shape. */
export function parseUsageError(err: any): UsageLimitInfo | null {
  const data = err?.response?.data
  // axios case
  if (data?.detail?.code === 'USAGE_LIMIT_EXCEEDED') return data.detail as UsageLimitInfo
  // SSE-fetch case where the body is already parsed
  if (data?.code === 'USAGE_LIMIT_EXCEEDED') return data as UsageLimitInfo
  return null
}
