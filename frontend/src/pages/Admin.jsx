import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Navigate } from 'react-router-dom'
import {
  Users, Shield, Plus, ChevronDown, Activity,
  Building2, Settings, Loader2, CheckCircle2,
  FileText, Search, Eye, Edit3, Lock,
} from 'lucide-react'
import { admin as adminApi } from '../api'
import { useAuthStore } from '../stores/authStore'

const ROLES = ['org_admin', 'editor', 'viewer', 'demo']
const ROLE_COLORS = {
  org_admin: 'bg-purple-100 text-purple-700 border-purple-200',
  editor:    'bg-blue-100   text-blue-700   border-blue-200',
  viewer:    'bg-slate-100  text-slate-600  border-slate-200',
  demo:      'bg-amber-100  text-amber-700  border-amber-200',
}
const ACTION_ICONS = {
  document_query:  { icon: Search,  color: 'text-blue-500',   bg: 'bg-blue-50'    },
  document_upload: { icon: FileText, color: 'text-green-500',  bg: 'bg-green-50'   },
  document_delete: { icon: FileText, color: 'text-red-500',    bg: 'bg-red-50'     },
  user_create:     { icon: Users,   color: 'text-purple-500', bg: 'bg-purple-50'  },
  role_change:     { icon: Shield,  color: 'text-amber-500',  bg: 'bg-amber-50'   },
  admin_action:    { icon: Settings, color: 'text-slate-500',  bg: 'bg-slate-50'   },
}

function UserRow({ user, onRoleChange }) {
  const [changing, setChanging] = useState(false)
  const [open, setOpen]         = useState(false)

  async function changeRole(role) {
    setChanging(true); setOpen(false)
    try { await onRoleChange(user.user_id, role) }
    finally { setChanging(false) }
  }

  return (
    <motion.tr
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors"
    >
      <td className="px-5 py-3.5">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-ida-grad flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {user.email.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <p className="text-sm font-medium text-slate-700">{user.email}</p>
            <p className="text-[11px] text-slate-400">{user.user_id?.slice(0, 8)}…</p>
          </div>
        </div>
      </td>
      <td className="px-5 py-3.5">
        <div className="relative inline-block">
          <button
            onClick={() => setOpen((v) => !v)}
            disabled={changing}
            className={`badge border flex items-center gap-1.5 ${ROLE_COLORS[user.role]} hover:opacity-80 transition-opacity`}
          >
            {changing ? <Loader2 size={10} className="animate-spin" /> : null}
            {user.role}
            <ChevronDown size={11} />
          </button>
          <AnimatePresence>
            {open && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="absolute z-20 mt-1 left-0 bg-white rounded-xl shadow-elevated border border-slate-100 py-1 min-w-[130px]"
              >
                {ROLES.map((r) => (
                  <button key={r} onClick={() => changeRole(r)}
                    className={`w-full text-left px-3 py-2 text-xs hover:bg-slate-50 transition-colors ${r === user.role ? 'font-semibold text-ida-blue' : 'text-slate-600'}`}>
                    {r}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </td>
      <td className="px-5 py-3.5">
        <span className={`badge ${user.is_active ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600'}`}>
          <span className={`status-dot ${user.is_active ? 'bg-emerald-400' : 'bg-red-400'}`} />
          {user.is_active ? 'Active' : 'Inactive'}
        </span>
      </td>
    </motion.tr>
  )
}

function AddUserModal({ onClose, onAdded }) {
  const [form, setForm]   = useState({ email: '', password: '', role: 'viewer' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      await adminApi.createUser(form)
      onAdded(); onClose()
    } catch (err) {
      setError(err.message)
    } finally { setLoading(false) }
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      className="fixed inset-0 bg-black/20 z-50 flex items-center justify-center p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}>
      <motion.div initial={{ scale: 0.95, y: 10 }} animate={{ scale: 1, y: 0 }}
        className="card w-full max-w-md p-6">
        <h3 className="font-display font-bold text-ida-navy mb-5">Add New User</h3>
        {error && <p className="text-xs text-red-500 mb-4 bg-red-50 rounded-lg p-3">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Email</label>
            <input type="email" className="input-field" placeholder="user@idaindore.org"
              value={form.email} onChange={set('email')} required />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Temporary Password</label>
            <input type="password" className="input-field" placeholder="Min. 6 characters"
              value={form.password} onChange={set('password')} required minLength={6} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Role</label>
            <select className="input-field" value={form.role} onChange={set('role')}>
              {ROLES.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary flex-1 flex items-center justify-center gap-2">
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              Add User
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  )
}

export default function Admin() {
  const user = useAuthStore((s) => s.user)
  if (user?.role !== 'org_admin') return <Navigate to="/chat" replace />

  const [users, setUsers]   = useState([])
  const [logs, setLogs]     = useState([])
  const [tenant, setTenant] = useState(null)
  const [tab, setTab]       = useState('users')
  const [showAdd, setShowAdd] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([adminApi.listUsers(), adminApi.auditLog(), adminApi.tenant()])
      .then(([u, l, t]) => { setUsers(u); setLogs(l); setTenant(t) })
      .finally(() => setLoading(false))
  }, [])

  async function handleRoleChange(userId, role) {
    await adminApi.updateRole(userId, role)
    setUsers((u) => u.map((x) => x.user_id === userId ? { ...x, role } : x))
  }

  const TABS = [
    { id: 'users',  label: 'Users',       icon: Users    },
    { id: 'logs',   label: 'Audit Log',   icon: Activity },
    { id: 'tenant', label: 'Workspace',   icon: Building2 },
  ]

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-purple-50 flex items-center justify-center">
            <Shield size={18} className="text-purple-600" />
          </div>
          <div>
            <h2 className="font-display font-semibold text-ida-navy text-sm">Admin Panel</h2>
            <p className="text-[11px] text-slate-400">User management · Audit logs · Workspace config</p>
          </div>
        </div>
        {tab === 'users' && (
          <button onClick={() => setShowAdd(true)} className="btn-primary flex items-center gap-1.5 text-sm py-2">
            <Plus size={14} /> Add User
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 px-6 pt-4 pb-0 bg-white border-b border-slate-100">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-xl border-b-2 transition-colors ${
              tab === id
                ? 'text-ida-blue border-ida-blue bg-ida-blue-pale'
                : 'text-slate-500 border-transparent hover:text-slate-700 hover:bg-slate-50'
            }`}>
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-5">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={24} className="animate-spin text-slate-300" />
          </div>
        ) : (
          <>
            {/* Users tab */}
            {tab === 'users' && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                <div className="card overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-100">
                        <th className="px-5 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">User</th>
                        <th className="px-5 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Role</th>
                        <th className="px-5 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <AnimatePresence>
                        {users.map((u) => (
                          <UserRow key={u.user_id} user={u} onRoleChange={handleRoleChange} />
                        ))}
                      </AnimatePresence>
                    </tbody>
                  </table>
                  {!users.length && (
                    <div className="py-12 text-center text-slate-400 text-sm">No users found</div>
                  )}
                </div>
              </motion.div>
            )}

            {/* Audit log tab */}
            {tab === 'logs' && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
                {logs.map((log) => {
                  const ac = ACTION_ICONS[log.action] || ACTION_ICONS.admin_action
                  const AIcon = ac.icon
                  return (
                    <div key={log.id} className="card p-4 flex items-start gap-3">
                      <div className={`w-8 h-8 rounded-lg ${ac.bg} flex items-center justify-center flex-shrink-0 mt-0.5`}>
                        <AIcon size={14} className={ac.color} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-700 capitalize">
                          {log.action.replace(/_/g, ' ')}
                        </p>
                        <p className="text-[11px] text-slate-400 mt-0.5 truncate">
                          {log.resource_type} · {log.resource_id?.slice(0, 12)}…
                          {log.log_metadata?.question && ` · "${log.log_metadata.question.slice(0, 60)}…"`}
                        </p>
                      </div>
                      <p className="text-[11px] text-slate-400 flex-shrink-0">
                        {new Date(log.timestamp).toLocaleString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  )
                })}
                {!logs.length && (
                  <div className="card py-12 text-center text-slate-400 text-sm">No audit logs yet</div>
                )}
              </motion.div>
            )}

            {/* Tenant tab */}
            {tab === 'tenant' && tenant && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                <div className="grid grid-cols-2 gap-5">
                  {[
                    { label: 'Organization Name', value: tenant.name,                icon: Building2, color: 'text-ida-navy'    },
                    { label: 'Plan Tier',          value: tenant.tier,               icon: Shield,    color: 'text-purple-600'  },
                    { label: 'Document Quota',     value: tenant.quota_documents,    icon: FileText,  color: 'text-blue-600'    },
                    { label: 'Daily Query Limit',  value: tenant.quota_queries_daily, icon: Activity, color: 'text-emerald-600' },
                    { label: 'LLM Provider',       value: tenant.llm_provider_override || 'Default', icon: Settings, color: 'text-amber-600' },
                    { label: 'Workspace ID',       value: tenant.tenant_id?.slice(0, 12) + '…', icon: Lock, color: 'text-slate-500' },
                  ].map(({ label, value, icon: Icon, color }) => (
                    <div key={label} className="card p-5">
                      <div className="flex items-center gap-2 mb-2">
                        <Icon size={14} className={color} />
                        <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{label}</p>
                      </div>
                      <p className="text-lg font-display font-bold text-slate-800 capitalize">{value}</p>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </>
        )}
      </div>

      <AnimatePresence>
        {showAdd && (
          <AddUserModal
            onClose={() => setShowAdd(false)}
            onAdded={() => adminApi.listUsers().then(setUsers)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
