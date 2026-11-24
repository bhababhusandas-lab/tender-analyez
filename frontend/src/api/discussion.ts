import { api } from './client'

export interface DiscussionMessage {
  role: 'user' | 'assistant'
  content: string
  job_id?: string
  version_number?: number | null
  version_label?: string | null
}

export interface DiscussionRequest {
  kind: 'pipeline' | 'roadmap'
  tender_text: string
  analysis_results: Record<string, string>
  final_briefing: string
  history?: DiscussionMessage[]
  question: string
  job_id?: string
}

export const sendDiscussion = async (req: DiscussionRequest): Promise<{ reply: string }> =>
  (await api.post('/api/v1/discussion', req)).data

export const fetchTenderDiscussion = async (tenderId: number): Promise<{ messages: DiscussionMessage[] }> =>
  (await api.get('/api/v1/discussion', { params: { tender_id: tenderId } })).data

export const fetchJobDiscussion = async (jobId: string): Promise<{ messages: DiscussionMessage[] }> =>
  (await api.get('/api/v1/discussion', { params: { job_id: jobId } })).data
