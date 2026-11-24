import { useState, useEffect } from 'react'
import { Save, CheckCircle, Plus, Trash2, Loader2, Building2 } from 'lucide-react'
import { fetchCompanies, createCompany, saveCompany, deleteCompany, emptyProfile, CompanyProfile as CP, KeyPerson, PastProject } from '../api/company'

function Field({ label, value, onChange, placeholder = '', type = 'text' }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 outline-none focus:border-gray-400 transition-colors" />
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-panel border border-gray-100 rounded-xl p-5 shadow-sm">
      <h3 className="font-semibold text-gray-900 text-sm mb-4 pb-2 border-b border-gray-100">{title}</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{children}</div>
    </div>
  )
}

export function CompanyProfile() {
  const [profile, setProfile] = useState<CP>(emptyProfile())
  const [companies, setCompanies] = useState<CP[]>([])
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  const [personnel, setPersonnel] = useState<KeyPerson[]>([])
  const [projects, setProjects] = useState<PastProject[]>([])

  useEffect(() => {
    fetchCompanies().then(items => {
      setCompanies(items)
      selectProfile(items[0])
      setLoading(false)
    })
  }, [])

  const selectProfile = (p: CP) => {
    setProfile(p)
    try { setPersonnel(JSON.parse(p.key_personnel || '[]')) } catch { setPersonnel([]) }
    try { setProjects(JSON.parse(p.past_projects || '[]')) } catch { setProjects([]) }
    setSaved(false)
  }

  const addCompany = async () => {
    const created = await createCompany({ ...emptyProfile(), company_name: `Company ${companies.length + 1}` })
    setCompanies(items => [...items, created])
    selectProfile(created)
  }

  const removeCompany = async () => {
    if (!profile.id || companies.length <= 1) return
    if (!window.confirm(`Delete ${profile.company_name || 'this company'}? This cannot be undone.`)) return
    await deleteCompany(profile.id)
    const remaining = companies.filter(c => c.id !== profile.id)
    setCompanies(remaining)
    selectProfile(remaining[0])
  }

  const set = (k: keyof CP) => (v: string) => setProfile(p => ({ ...p, [k]: v }))

  const submit = async () => {
    setSaving(true)
    const payload = { ...profile, key_personnel: JSON.stringify(personnel), past_projects: JSON.stringify(projects) }
    if (!profile.id) return
    const updated = await saveCompany(profile.id, payload)
    setProfile(updated)
    setCompanies(items => items.map(c => c.id === updated.id ? updated : c))
    setSaving(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  if (loading) return <div className="text-center py-20 text-gray-400 text-sm">Loading profile…</div>

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-5">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Company Profile</h1>
          <p className="text-sm text-gray-500 mt-0.5">Add every company you manage, then select or compare them when analyzing a tender</p>
        </div>
        <button onClick={submit} disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-xl hover:bg-gray-700 disabled:opacity-50 transition-colors">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle className="w-4 h-4 text-green-400" /> : <Save className="w-4 h-4" />}
          {saving ? 'Saving…' : saved ? 'Saved!' : 'Save Profile'}
        </button>
      </div>

      <div className="bg-panel border border-gray-100 rounded-xl p-4 shadow-sm">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Your companies</h2>
            <p className="text-xs text-gray-500">All 11 AI agents keep each company's credentials separate.</p>
          </div>
          <button onClick={addCompany} className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-blue-700 bg-blue-50 rounded-lg hover:bg-blue-100">
            <Plus className="w-3.5 h-3.5" /> Add Company
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {companies.map((company, index) => (
            <button key={company.id} onClick={() => selectProfile(company)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm ${company.id === profile.id ? 'border-orange-400 bg-orange-50 text-gray-900' : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}>
              <Building2 className="w-4 h-4" /> {company.company_name || `Company ${index + 1}`}
            </button>
          ))}
          {companies.length > 1 && (
            <button onClick={removeCompany} className="ml-auto flex items-center gap-1.5 px-3 py-2 text-xs text-red-600 hover:bg-red-50 rounded-lg">
              <Trash2 className="w-3.5 h-3.5" /> Delete selected
            </button>
          )}
        </div>
      </div>

      {/* Basic Info */}
      <Section title="🏢 Basic Information">
        <div className="sm:col-span-2"><Field label="Company Name *" value={profile.company_name} onChange={set('company_name')} placeholder="Unique Type Pvt Ltd" /></div>
        <Field label="Company Type" value={profile.company_type} onChange={set('company_type')} placeholder="Pvt Ltd / Partnership / Proprietorship" />
        <Field label="Year Established" value={profile.established_year} onChange={set('established_year')} placeholder="2015" />
        <div className="sm:col-span-2"><Field label="Registered Address" value={profile.address} onChange={set('address')} placeholder="Full address" /></div>
        <Field label="Website" value={profile.website} onChange={set('website')} placeholder="www.yourcompany.com" />
      </Section>

      {/* Registrations */}
      <Section title="📋 Registrations & Certifications">
        <Field label="GST Number *" value={profile.gst_no} onChange={set('gst_no')} placeholder="36XXXXXXXXXXXXX" />
        <Field label="PAN Number *" value={profile.pan_no} onChange={set('pan_no')} placeholder="AAAAA0000A" />
        <Field label="CIN Number" value={profile.cin_no} onChange={set('cin_no')} placeholder="U74999TS2015PTC000000" />
        <Field label="MSME Udyam Number" value={profile.msme_no} onChange={set('msme_no')} placeholder="UDYAM-TS-00-0000000" />
        <Field label="MSME Category" value={profile.msme_category} onChange={set('msme_category')} placeholder="Micro / Small / Medium" />
        <Field label="ISO Certifications" value={profile.iso_certs} onChange={set('iso_certs')} placeholder="ISO 9001:2015, ISO 27001:2013" />
        <div className="sm:col-span-2"><Field label="Other Certifications" value={profile.other_certs} onChange={set('other_certs')} placeholder="BIS, STQC, DPIIT Startup recognition, etc." /></div>
      </Section>

      {/* Financial */}
      <Section title="💰 Financial Details">
        <Field label="Turnover FY 2023-24 (₹)" value={profile.turnover_y1} onChange={set('turnover_y1')} placeholder="1,50,00,000" />
        <Field label="Turnover FY 2022-23 (₹)" value={profile.turnover_y2} onChange={set('turnover_y2')} placeholder="1,20,00,000" />
        <Field label="Turnover FY 2021-22 (₹)" value={profile.turnover_y3} onChange={set('turnover_y3')} placeholder="90,00,000" />
        <Field label="Net Worth (₹)" value={profile.net_worth} onChange={set('net_worth')} placeholder="50,00,000" />
        <Field label="Max EMD We Can Handle (₹)" value={profile.emd_capacity} onChange={set('emd_capacity')} placeholder="10,00,000" />
        <Field label="Bank BG Limit (₹)" value={profile.bg_limit} onChange={set('bg_limit')} placeholder="50,00,000" />
        <Field label="Bank Name" value={profile.bank_name} onChange={set('bank_name')} placeholder="State Bank of India, Hyderabad" />
      </Section>

      {/* Portals */}
      <Section title="🌐 Portal Registrations">
        <Field label="GeM Seller ID" value={profile.gem_seller_id} onChange={set('gem_seller_id')} placeholder="SELLER0000000000" />
        <Field label="CPPP Registered" value={profile.cppp_registered} onChange={set('cppp_registered')} placeholder="Yes / No / Vendor ID" />
        <Field label="eProcurement Telangana" value={profile.telangana_reg} onChange={set('telangana_reg')} placeholder="Vendor ID or Yes/No" />
        <Field label="Other Portals" value={profile.other_portals} onChange={set('other_portals')} placeholder="IREPS, MES, PWD, etc." />
      </Section>

      {/* Work Categories */}
      <Section title="⚙️ Work Categories & Geography">
        <div className="sm:col-span-2">
          <label className="block text-xs font-medium text-gray-500 mb-1">Work/Supply Categories (comma separated)</label>
          <textarea value={profile.work_categories} onChange={e => set('work_categories')(e.target.value)}
            placeholder="Office Furniture, IT Equipment, Civil Works, Security Services, Housekeeping, IT Software..."
            rows={3} className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 outline-none focus:border-gray-400 resize-none" />
        </div>
        <div className="sm:col-span-2">
          <Field label="States Where Registered/Active" value={profile.states_registered} onChange={set('states_registered')} placeholder="Telangana, Andhra Pradesh, Karnataka, Maharashtra" />
        </div>
      </Section>

      {/* Key Personnel */}
      <div className="bg-panel border border-gray-100 rounded-xl p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4 pb-2 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 text-sm">👥 Key Personnel</h3>
          <button onClick={() => setPersonnel(p => [...p, { name: '', designation: '', qualification: '', experience: '' }])}
            className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 font-medium">
            <Plus className="w-3.5 h-3.5" /> Add Person
          </button>
        </div>
        {personnel.length === 0 && <p className="text-xs text-gray-400">No personnel added. These go into technical proposals as your team credentials.</p>}
        <div className="space-y-3">
          {personnel.map((p, i) => (
            <div key={i} className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-gray-50 rounded-lg p-3 relative">
              <input value={p.name} onChange={e => setPersonnel(arr => arr.map((x, j) => j === i ? { ...x, name: e.target.value } : x))}
                placeholder="Full name" className="text-sm border border-gray-200 rounded px-2 py-1.5 outline-none" />
              <input value={p.designation} onChange={e => setPersonnel(arr => arr.map((x, j) => j === i ? { ...x, designation: e.target.value } : x))}
                placeholder="Designation" className="text-sm border border-gray-200 rounded px-2 py-1.5 outline-none" />
              <input value={p.qualification} onChange={e => setPersonnel(arr => arr.map((x, j) => j === i ? { ...x, qualification: e.target.value } : x))}
                placeholder="Qualification (B.Tech, MBA…)" className="text-sm border border-gray-200 rounded px-2 py-1.5 outline-none" />
              <div className="flex gap-2">
                <input value={p.experience} onChange={e => setPersonnel(arr => arr.map((x, j) => j === i ? { ...x, experience: e.target.value } : x))}
                  placeholder="Experience (e.g. 12 years)" className="flex-1 text-sm border border-gray-200 rounded px-2 py-1.5 outline-none" />
                <button onClick={() => setPersonnel(arr => arr.filter((_, j) => j !== i))} className="text-red-400 hover:text-red-600">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Past Projects */}
      <div className="bg-panel border border-gray-100 rounded-xl p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4 pb-2 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 text-sm">🏆 Past Projects / Experience</h3>
          <button onClick={() => setProjects(p => [...p, { name: '', client: '', value: '', year: '', description: '' }])}
            className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 font-medium">
            <Plus className="w-3.5 h-3.5" /> Add Project
          </button>
        </div>
        {projects.length === 0 && <p className="text-xs text-gray-400">No projects added. These are used by Technical Expert AI to prove experience and match eligibility criteria.</p>}
        <div className="space-y-3">
          {projects.map((p, i) => (
            <div key={i} className="bg-gray-50 rounded-lg p-3 space-y-2">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <input value={p.name} onChange={e => setProjects(arr => arr.map((x, j) => j === i ? { ...x, name: e.target.value } : x))}
                  placeholder="Project name" className="text-sm border border-gray-200 rounded px-2 py-1.5 outline-none" />
                <input value={p.client} onChange={e => setProjects(arr => arr.map((x, j) => j === i ? { ...x, client: e.target.value } : x))}
                  placeholder="Client / Dept" className="text-sm border border-gray-200 rounded px-2 py-1.5 outline-none" />
                <input value={p.value} onChange={e => setProjects(arr => arr.map((x, j) => j === i ? { ...x, value: e.target.value } : x))}
                  placeholder="Value (₹)" className="text-sm border border-gray-200 rounded px-2 py-1.5 outline-none" />
                <div className="flex gap-2">
                  <input value={p.year} onChange={e => setProjects(arr => arr.map((x, j) => j === i ? { ...x, year: e.target.value } : x))}
                    placeholder="Year" className="flex-1 text-sm border border-gray-200 rounded px-2 py-1.5 outline-none" />
                  <button onClick={() => setProjects(arr => arr.filter((_, j) => j !== i))} className="text-red-400 hover:text-red-600">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <textarea value={p.description} onChange={e => setProjects(arr => arr.map((x, j) => j === i ? { ...x, description: e.target.value } : x))}
                placeholder="Brief description (scope, deliverables, outcome)" rows={2}
                className="w-full text-sm border border-gray-200 rounded px-2 py-1.5 outline-none resize-none" />
            </div>
          ))}
        </div>
      </div>

      {/* Save footer */}
      <div className="flex justify-end pt-2">
        <button onClick={submit} disabled={saving}
          className="flex items-center gap-2 px-6 py-3 bg-gray-900 text-white text-sm font-medium rounded-xl hover:bg-gray-700 disabled:opacity-50 transition-colors">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle className="w-4 h-4 text-green-400" /> : <Save className="w-4 h-4" />}
          {saving ? 'Saving…' : saved ? 'Profile Saved!' : 'Save Company Profile'}
        </button>
      </div>
    </div>
  )
}
