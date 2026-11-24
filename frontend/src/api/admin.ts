import { api } from './client'

export interface AdminUserRow {
  id: number
  email: string
  full_name: string
  company_name: string
  phone: string
  plan: string
  trial_ends_at: string | null
  is_admin: boolean
  is_active: boolean
  email_verified: boolean
  created_at: string
  last_login_at: string | null
  bids_count: number
  documents_count: number
  usage_total: number
  usage_24h: number
  usage_30d: number
}

export const forceVerifyUser = async (id: number) =>
  (await api.post(`/api/v1/admin/users/${id}/force-verify`)).data

export const peekVerificationCode = async (id: number) =>
  (await api.get(`/api/v1/admin/users/${id}/verification-code`)).data

export interface AdminStats {
  total_users: number
  active_users: number
  trial_users: number
  new_this_week: number
  active_this_week: number
  plan_breakdown: Record<string, number>
  total_bids: number
  total_documents: number
  total_past_bids: number
}

export const fetchAdminUsers = async (): Promise<AdminUserRow[]> =>
  (await api.get('/api/v1/admin/users')).data

export const fetchAdminStats = async (): Promise<AdminStats> =>
  (await api.get('/api/v1/admin/stats')).data

export const updateUserPlan = async (id: number, plan: string) =>
  (await api.patch(`/api/v1/admin/users/${id}/plan`, { plan })).data

export const toggleUserActive = async (id: number) =>
  (await api.patch(`/api/v1/admin/users/${id}/toggle-active`)).data
