import { useState, useEffect, useCallback } from 'react'
import { Navigate } from 'react-router-dom'
import {
  Building2, Plus, RotateCcw, Users, FileText, ShieldAlert, Loader2, X, Ban, CheckCircle2, ChevronRight,
} from 'lucide-react'
import { platform as platformApi } from '../api'
import { useAuthStore } from '../stores/authStore'

const TIERS = ['demo', 'starter', 'pro', 'enterprise']
const ROLES = ['org_admin', 'editor', 'viewer', 'demo', 'reception', 'doctor']
const DOMAINS = [['generic', 'General'], ['legal', 'Legal'], ['ca', 'CA / Tax'], ['clinic', 'Clinic / Healthcare']]
const TIER_CLS = {
  demo: 'bg-slate-50 text-slate-500 border-slate-200',
  starter: 'bg-blue-50 text-blue-600 border-blue-100',
  pro: 'bg-violet-50 text-violet-600 border-violet-100',
  enterprise: 'bg-amber-50 text-amber-700 border-amber-100',
}

export default function PlatformConsole() {
  const user = useAuthStore(s => s.user)
  const [orgs, setOrgs]         = useState([])
  const [selected, setSelected] = useState(null)   // org detail
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [creating, setCreating] = useState(false)

  const loadOrgs = useCallback(async () => {
    setLoading(true)
    try { setOrgs(await platformApi.listOrgs()); setError('') }
    catch (e) { setError(e.message || 'Could not load organizations.') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { if (user?.is_platform_admin) loadOrgs() }, [user, loadOrgs])

  // Gate: only platform admins may see this console.
  if (!user?.is_platform_admin) return <Navigate to="/chat" replace />

  async function openOrg(id) {
    setError('')
    try { setSelected(await platformApi.getOrg(id)) }
    catch (e) { setError(e.message || 'Could not load organization.') }
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      <div className="flex items-center gap-3 px-6 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
          <Building2 size={18} className="text-duck-blue" />
        </div>
        <div className="flex-1">
          <h2 className="font-display font-semibold text-duck-navy text-sm">Platform Console</h2>
          <p className="text-[11px] text-slate-400">Manage all organizations, members, plans and limits.</p>
        </div>
        <button onClick={() => setCreating(true)} className="btn-primary flex items-center gap-1.5 text-sm">
          <Plus size={15} /> New organization
        </button>
      </div>

      {error && (
        <div className="mx-6 mt-4 flex items-center gap-2 bg-red-50 border border-red-100 rounded-xl px-4 py-2.5 text-sm text-red-600">
          <div className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />{error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto scrollbar-thin p-6">
        {selected ? (
          <OrgDetail org={selected} onBack={() => { setSelected(null); loadOrgs() }} onRefresh={openOrg} onError={setError} />
        ) : loading ? (
          <div className="flex items-center gap-2 text-slate-400 text-sm"><Loader2 size={16} className="animate-spin" /> Loading organizations…</div>
        ) : (
          <div className="bg-white rounded-2xl border border-slate-200 overflow-x-auto scrollbar-thin">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-slate-50 text-slate-500 text-[11px] uppercase tracking-wider">
                  <th className="text-left font-semibold px-5 py-3">Organization</th>
                  <th className="text-left font-semibold px-5 py-3">Plan</th>
                  <th className="text-left font-semibold px-5 py-3">Status</th>
                  <th className="text-left font-semibold px-5 py-3">Users</th>
                  <th className="text-left font-semibold px-5 py-3">Docs</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {orgs.map(o => (
                  <tr key={o.id} onClick={() => openOrg(o.id)}
                    className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer">
                    <td className="px-5 py-3 font-medium text-duck-navy">{o.name}</td>
                    <td className="px-5 py-3">
                      <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full border ${TIER_CLS[o.tier] || TIER_CLS.starter}`}>{o.tier}</span>
                    </td>
                    <td className="px-5 py-3">
                      {o.is_active
                        ? <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600"><CheckCircle2 size={12} /> Active</span>
                        : <span className="inline-flex items-center gap-1 text-[11px] text-red-500"><Ban size={12} /> Suspended</span>}
                    </td>
                    <td className="px-5 py-3 text-slate-600">{o.user_count}</td>
                    <td className="px-5 py-3 text-slate-600">{o.document_count}</td>
                    <td className="px-5 py-3 text-right"><ChevronRight size={14} className="text-slate-300" /></td>
                  </tr>
                ))}
                {orgs.length === 0 && (
                  <tr><td colSpan={6} className="px-5 py-12 text-center text-slate-400">No organizations yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {creating && <CreateOrgModal onClose={() => setCreating(false)} onCreated={() => { setCreating(false); loadOrgs() }} />}
    </div>
  )
}

function CreateOrgModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ name: '', tier: 'starter', domain: 'generic', quota_documents: 100, quota_queries_daily: 1000, admin_email: '', admin_password: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr]   = useState('')
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function submit(e) {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      await platformApi.createOrg({
        ...form,
        quota_documents: Number(form.quota_documents),
        quota_queries_daily: Number(form.quota_queries_daily),
      })
      onCreated()
    } catch (e2) { setErr(e2.message || 'Create failed.'); setBusy(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display font-bold text-duck-navy">New organization</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        {err && <div className="mb-3 text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">{err}</div>}
        <form onSubmit={submit} className="space-y-3">
          <Field label="Organization name"><input required value={form.name} onChange={e => set('name', e.target.value)} className="input-field" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Vertical">
              <select value={form.domain} onChange={e => set('domain', e.target.value)} className="input-field">
                {DOMAINS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
              </select>
            </Field>
            <Field label="Plan">
              <select value={form.tier} onChange={e => set('tier', e.target.value)} className="input-field">
                {TIERS.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Docs quota"><input type="number" min="0" value={form.quota_documents} onChange={e => set('quota_documents', e.target.value)} className="input-field" /></Field>
          <Field label="Daily query quota"><input type="number" min="0" value={form.quota_queries_daily} onChange={e => set('quota_queries_daily', e.target.value)} className="input-field" /></Field>
          <div className="pt-1 border-t border-slate-100" />
          <Field label="Org admin email"><input required type="email" value={form.admin_email} onChange={e => set('admin_email', e.target.value)} className="input-field" /></Field>
          <Field label="Org admin password (min 8)"><input required type="password" value={form.admin_password} onChange={e => set('admin_password', e.target.value)} className="input-field" /></Field>
          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={busy} className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50">
              {busy ? <><Loader2 size={15} className="animate-spin" /> Creating…</> : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function OrgDetail({ org, onBack, onRefresh, onError }) {
  const [tier, setTier]   = useState(org.tier)
  const [qd, setQd]       = useState(org.quota_documents)
  const [qq, setQq]       = useState(org.quota_queries_daily)
  const [saving, setSaving] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [moving, setMoving] = useState(null)   // member being moved to another org

  async function saveOrg(patch) {
    setSaving(true)
    try { await platformApi.updateOrg(org.id, patch); await onRefresh(org.id) }
    catch (e) { onError(e.message || 'Update failed.') }
    finally { setSaving(false) }
  }
  async function toggleSuspend() { await saveOrg({ is_active: !org.is_active }) }
  async function saveTierQuota() { await saveOrg({ tier, quota_documents: Number(qd), quota_queries_daily: Number(qq) }) }

  async function setRole(uid, role) {
    try { await platformApi.updateMember(org.id, uid, { role }); await onRefresh(org.id) }
    catch (e) { onError(e.message || 'Update failed.') }
  }
  async function setActive(uid, is_active) {
    try { await platformApi.updateMember(org.id, uid, { is_active }); await onRefresh(org.id) }
    catch (e) { onError(e.message || 'Update failed.') }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
            <RotateCcw size={13} /> All organizations
          </button>
          <h3 className="font-display font-bold text-duck-navy text-lg">{org.name}</h3>
          {!org.is_active && <span className="inline-flex items-center gap-1 text-[11px] text-red-500"><Ban size={12} /> Suspended</span>}
        </div>
        <button onClick={toggleSuspend} disabled={saving}
          className={`text-xs font-semibold px-3 py-2 rounded-lg border disabled:opacity-50 ${org.is_active ? 'text-red-600 border-red-200 hover:bg-red-50' : 'text-emerald-600 border-emerald-200 hover:bg-emerald-50'}`}>
          {org.is_active ? 'Suspend org' : 'Reactivate org'}
        </button>
      </div>

      {/* usage */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <Stat icon={Users} label="Members" value={org.members.length} />
        <Stat icon={FileText} label="Documents" value={org.usage.documents} />
        <Stat icon={ShieldAlert} label="Queries today" value={org.usage.queries_today} />
      </div>

      {/* plan + quotas */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 mb-4">
        <h4 className="font-display font-semibold text-duck-navy text-sm mb-3">Plan & quotas</h4>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
          <Field label="Plan">
            <select value={tier} onChange={e => setTier(e.target.value)} className="input-field">
              {TIERS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Docs quota"><input type="number" min="0" value={qd} onChange={e => setQd(e.target.value)} className="input-field" /></Field>
          <Field label="Daily queries"><input type="number" min="0" value={qq} onChange={e => setQq(e.target.value)} className="input-field" /></Field>
          <button onClick={saveTierQuota} disabled={saving} className="btn-primary flex items-center justify-center gap-2 disabled:opacity-50">
            {saving ? <Loader2 size={15} className="animate-spin" /> : 'Save'}
          </button>
        </div>
        <RateLimitEditor org={org} onError={onError} />
      </div>

      {/* members */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
          <h4 className="font-display font-semibold text-duck-navy text-sm">Members</h4>
          <button onClick={() => setAddOpen(true)} className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
            <Plus size={13} /> Add member
          </button>
        </div>
        <table className="w-full text-sm">
          <tbody>
            {org.members.map(m => (
              <tr key={m.user_id} className="border-t border-slate-50">
                <td className="px-5 py-3">
                  <span className="text-slate-700">{m.email}</span>
                  {m.is_platform_admin && <span className="ml-2 text-[10px] font-semibold text-violet-600">platform</span>}
                </td>
                <td className="px-5 py-3">
                  <select value={m.role} onChange={e => setRole(m.user_id, e.target.value)} className="input-field py-1 text-xs">
                    {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td className="px-5 py-3 text-right whitespace-nowrap">
                  <button onClick={() => setMoving(m)} className="text-xs font-semibold text-duck-blue hover:underline mr-3">
                    Move
                  </button>
                  <button onClick={() => setActive(m.user_id, !m.is_active)}
                    className={`text-xs font-semibold ${m.is_active ? 'text-red-500 hover:underline' : 'text-emerald-600 hover:underline'}`}>
                    {m.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {addOpen && <AddMemberModal orgId={org.id} onClose={() => setAddOpen(false)} onAdded={() => { setAddOpen(false); onRefresh(org.id) }} onError={onError} />}
      {moving && <MoveMemberModal member={moving} fromOrgId={org.id} onClose={() => setMoving(null)} onMoved={() => { setMoving(null); onRefresh(org.id) }} onError={onError} />}
    </div>
  )
}

function MoveMemberModal({ member, fromOrgId, onClose, onMoved, onError }) {
  const [orgs, setOrgs]   = useState([])
  const [target, setTarget] = useState('')
  const [busy, setBusy]   = useState(false)
  useEffect(() => {
    platformApi.listOrgs().then(list => setOrgs(list.filter(o => o.id !== fromOrgId))).catch(() => {})
  }, [fromOrgId])
  async function submit(e) {
    e.preventDefault(); if (!target) return; setBusy(true)
    try { await platformApi.moveMember(fromOrgId, member.user_id, { target_tenant_id: target }); onMoved() }
    catch (e2) { onError(e2.message || 'Move failed.'); setBusy(false) }
  }
  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display font-bold text-duck-navy">Move member</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        <p className="text-xs text-slate-500 mb-3">Move <span className="font-medium text-slate-700">{member.email}</span> to another organization. Documents they uploaded stay with the current org.</p>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Target organization">
            <select value={target} onChange={e => setTarget(e.target.value)} className="input-field" required>
              <option value="">Select an organization…</option>
              {orgs.map(o => <option key={o.id} value={o.id}>{o.name} ({o.tier})</option>)}
            </select>
          </Field>
          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={busy || !target} className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50">
              {busy ? <><Loader2 size={15} className="animate-spin" /> Moving…</> : 'Move'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function RateLimitEditor({ org, onError }) {
  const [rl, setRl] = useState(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    platformApi.getRateLimit(org.id).then(setRl).catch(() => {})
  }, [org.id])
  if (!rl) return null
  const set = (k, v) => setRl(r => ({ ...r, [k]: v }))
  async function save() {
    setSaving(true)
    try {
      await platformApi.setRateLimit(org.id, {
        queries_per_minute: Number(rl.queries_per_minute),
        queries_per_day: Number(rl.queries_per_day),
        ingestion_per_hour: Number(rl.ingestion_per_hour),
        max_concurrent_queries: Number(rl.max_concurrent_queries),
      })
    } catch (e) { onError(e.message || 'Rate-limit update failed.') }
    finally { setSaving(false) }
  }
  return (
    <div className="mt-4 pt-4 border-t border-slate-100">
      <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Rate limits {rl.is_default && <span className="text-slate-400 normal-case font-normal">(defaults)</span>}</p>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 items-end">
        <Field label="Per minute"><input type="number" min="1" value={rl.queries_per_minute} onChange={e => set('queries_per_minute', e.target.value)} className="input-field" /></Field>
        <Field label="Per day"><input type="number" min="1" value={rl.queries_per_day} onChange={e => set('queries_per_day', e.target.value)} className="input-field" /></Field>
        <Field label="Uploads/hr"><input type="number" min="1" value={rl.ingestion_per_hour} onChange={e => set('ingestion_per_hour', e.target.value)} className="input-field" /></Field>
        <Field label="Concurrent"><input type="number" min="1" value={rl.max_concurrent_queries} onChange={e => set('max_concurrent_queries', e.target.value)} className="input-field" /></Field>
        <button onClick={save} disabled={saving} className="btn-ghost border border-slate-200 flex items-center justify-center gap-2 disabled:opacity-50">
          {saving ? <Loader2 size={15} className="animate-spin" /> : 'Save limits'}
        </button>
      </div>
    </div>
  )
}

function AddMemberModal({ orgId, onClose, onAdded, onError }) {
  const [form, setForm] = useState({ email: '', password: '', role: 'viewer' })
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  async function submit(e) {
    e.preventDefault(); setBusy(true)
    try { await platformApi.addMember(orgId, form); onAdded() }
    catch (e2) { onError(e2.message || 'Add member failed.'); setBusy(false) }
  }
  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display font-bold text-duck-navy">Add member</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Email"><input required type="email" value={form.email} onChange={e => set('email', e.target.value)} className="input-field" /></Field>
          <Field label="Temporary password (min 8)"><input required type="password" value={form.password} onChange={e => set('password', e.target.value)} className="input-field" /></Field>
          <Field label="Role">
            <select value={form.role} onChange={e => set('role', e.target.value)} className="input-field">
              {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>
          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={busy} className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50">
              {busy ? <><Loader2 size={15} className="animate-spin" /> Adding…</> : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-slate-600 mb-1.5">{label}</label>
      {children}
    </div>
  )
}

function Stat({ icon: Icon, label, value }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4 flex items-center gap-3">
      <div className="w-9 h-9 rounded-lg bg-duck-blue-pale flex items-center justify-center">
        <Icon size={16} className="text-duck-blue" />
      </div>
      <div>
        <p className="text-lg font-bold text-duck-navy leading-none">{value}</p>
        <p className="text-[11px] text-slate-400 mt-1">{label}</p>
      </div>
    </div>
  )
}
