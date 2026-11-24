import { api } from './client'

export interface KeyPerson { name: string; designation: string; qualification: string; experience: string }
export interface PastProject { name: string; client: string; value: string; year: string; description: string }

export interface CompanyProfile {
  id?: number; user_id?: number
  company_name: string; company_type: string; established_year: string; website: string; address: string
  gst_no: string; pan_no: string; cin_no: string; msme_no: string; msme_category: string
  iso_certs: string; other_certs: string
  turnover_y1: string; turnover_y2: string; turnover_y3: string
  net_worth: string; emd_capacity: string; bg_limit: string; bank_name: string
  gem_seller_id: string; cppp_registered: string; telangana_reg: string; other_portals: string
  work_categories: string; states_registered: string
  key_personnel: string; past_projects: string
}

export const emptyProfile = (): CompanyProfile => ({
  company_name: '', company_type: '', established_year: '', website: '', address: '',
  gst_no: '', pan_no: '', cin_no: '', msme_no: '', msme_category: '',
  iso_certs: '', other_certs: '',
  turnover_y1: '', turnover_y2: '', turnover_y3: '',
  net_worth: '', emd_capacity: '', bg_limit: '', bank_name: '',
  gem_seller_id: '', cppp_registered: '', telangana_reg: '', other_portals: '',
  work_categories: '', states_registered: '',
  key_personnel: '[]', past_projects: '[]',
})

export const fetchProfile = async (): Promise<CompanyProfile> => (await api.get('/api/v1/company')).data
export const saveProfile = async (p: CompanyProfile): Promise<CompanyProfile> => (await api.put('/api/v1/company', p)).data
export const fetchCompanies = async (): Promise<CompanyProfile[]> => (await api.get('/api/v1/companies')).data
export const createCompany = async (p: CompanyProfile): Promise<CompanyProfile> => (await api.post('/api/v1/companies', p)).data
export const saveCompany = async (id: number, p: CompanyProfile): Promise<CompanyProfile> => (await api.put(`/api/v1/companies/${id}`, p)).data
export const deleteCompany = async (id: number): Promise<void> => { await api.delete(`/api/v1/companies/${id}`) }
