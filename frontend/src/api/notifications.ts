import { api } from './client'
import type { RunKind } from './tenders'

export type AlertStage = '7' | '5' | '3' | '1' | 'today' | 'overdue'

export interface DeadlineNotification {
  tender_id: number
  name: string
  deadline_iso: string
  deadline_text: string
  days_left: number
  stage: AlertStage
  message: string
  unread: boolean
  latest_kind: RunKind
  latest_job_id: string | null
}

export interface NotificationsResponse {
  unread_count: number
  items: DeadlineNotification[]
}

export const fetchNotifications = async (): Promise<NotificationsResponse> =>
  (await api.get('/api/v1/notifications')).data

/** Marks one tender's current stage read, or every current notification when no id is given. */
export const markNotificationsRead = async (tenderId?: number): Promise<void> => {
  await api.post('/api/v1/notifications/read', tenderId === undefined ? {} : { tender_id: tenderId })
}
