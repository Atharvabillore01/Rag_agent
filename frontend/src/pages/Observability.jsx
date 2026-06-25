import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Navigate } from 'react-router-dom'
import {
  Activity, Search, LogIn, Users, Shield,
  FileText, Settings, Loader2, RefreshCw,
  TrendingUp, Clock, Filter,
} from 'lucide-react'
import { admin as adminApi } from '../api'
import { useAuthStore } from '../stores/authStore'

// ── helpers ──────────────────────────────────────────────────────────────────

function relativeTime(iso) {
  const diff = (Date.now() - new Date(iso)) / 1000
  if (diff < 60)   return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

function fullTime(iso) {
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function initials(email = '') {
  return email.slice(0, 2).toUpperCase()
}

const ACTION_CONFIG = {
  document_query:  { label: 'Query',   icon: Search,   bg: 'bg-blue-50',   text: 'text-blue-600',   dot: 'bg-blue-400'   },
  user_login:      { label: 'Login',   icon: LogIn,    bg: 'bg-emerald-50', text: 'text-emerald-600', dot: 'bg-emerald-400' },
  document_upload: { label: 'Upload',  icon: FileText, bg: 'bg-violet-50', text: 'text-violet-600', dot: 'bg-violet-400' },
  document_delete: { label: 'Delete',  icon: FileText, bg: 'bg-red-50',    text: 'text-red-600',    dot: 'bg-red-400'    },
  user_create:     { label: 'New User',icon: Users,    bg: 'bg-purple-50', text: 'text-purple-600', dot: 'bg-purple-400' },
  role_change:     { label: 'Role',    icon: Shield,   bg: 'bg-amber-50',  text: 'text-amber-600',  dot: 'bg-amber-400'  },
  admin_action:    { label: 'Admin',   icon: Settings, bg: 'bg-slate-50',  text: 'text-slate-600',  dot: 'bg-slate-400'  },
}
const DEFAULT_ACTION = { label: 'Event', icon: Activity, bg: 'bg-slate-50', text: 'text-slate-600', dot: 'bg-slate-300' }

function getActionMeta(action) {
  return ACTION_CONFIG[action] || DEFAULT_ACTION
}

function logDescription(log) {
  const q = log.metadata?.question
  const email = log.metadata?.email
  if (log.action === 'document_query' && q)  return `"${q.slice(0, 80)}${q.length > 80 ? '…' : ''}"`
  if (log.action === 'user_login')            return `Signed in${email ? ` as ${email}` : ''}`
  if (log.action === 'document_upload')       return log.metadata?.filename || 'File uploaded'
  if (log.action === 'document_delete')       return log.metadata?.filename || 'File deleted'
  if (log.action === 'user_create')           return `Created user ${log.metadata?.email || ''}`
  if (log.action === 'role_change')           return `Role changed: ${log.metadata?.old_role} → ${log.metadata?.new_role}`
  return log.action.replace(/_/g, ' ')
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, color, sub }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="card p-5 flex items-start gap-4"
    >
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
        <Icon size={18} className="text-white" />
      </div>
      <div>
        <p className="text-2xl font-display font-bold text-slate-800">{value ?? '—'}</p>
        <p className="text-xs font-semibold text-slate-500 mt-0.5">{label}</p>
        {sub && <p className="text-[11px] text-slate-400 mt-0.5">{sub}</p>}
      </div>
    </motion.div>
  )
}

// ── Log row ───────────────────────────────────────────────────────────────────

function LogRow({ log }) {
  const [expanded, setExpanded] = useState(false)
  const meta = getActionMeta(log.action)
  const Icon = meta.icon

  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50/60 transition-colors cursor-pointer rounded-xl"
      onClick={() => setExpanded(e => !e)}
    >
      {/* Action icon */}
      <div className={`w-8 h-8 rounded-lg ${meta.bg} flex items-center justify-center flex-shrink-0 mt-0.5`}>
        <Icon size={14} className={meta.text} />
      </div>

      {/* User avatar + details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-ida-grad flex items-center justify-center flex-shrink-0">
            <span className="text-white text-[8px] font-bold">{initials(log.user_email)}</span>
          </div>
          <span className="text-xs font-semibold text-slate-700 truncate">{log.user_email}</span>
          {log.user_role && (
            <span className="text-[10px] text-slate-400 bg-slate-100 rounded px-1.5 py-0.5 flex-shrink-0">
              {log.user_role}
            </span>
          )}
        </div>
        <p className={`text-xs mt-1 ${log.action === 'document_query' ? 'text-slate-600 italic' : 'text-slate-500'} truncate`}>
          {logDescription(log)}
        </p>
        <AnimatePresence>
          {expanded && log.metadata && (
            <motion.pre
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="mt-2 text-[11px] text-slate-500 bg-slate-50 rounded-lg p-2.5 overflow-x-auto whitespace-pre-wrap font-mono"
            >
              {JSON.stringify(log.metadata, null, 2)}
            </motion.pre>
          )}
        </AnimatePresence>
      </div>

      {/* Timestamp */}
      <div className="text-right flex-shrink-0">
        <p className="text-[11px] font-medium text-slate-400">{relativeTime(log.timestamp)}</p>
        <p className="text-[10px] text-slate-300 mt-0.5">{fullTime(log.timestamp).split(',')[0]}</p>
      </div>
    </motion.div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

const FILTER_TABS = [
  { id: '',                label: 'All',     icon: Activity },
  { id: 'document_query', label: 'Queries', icon: Search   },
  { id: 'user_login',     label: 'Logins',  icon: LogIn    },
  { id: 'document_upload',label: 'Uploads', icon: FileText },
]

export default function Observability() {
  const user = useAuthStore(s => s.user)
  if (user?.role !== 'org_admin') return <Navigate to="/chat" replace />

  const [data, setData]         = useState(null)
  const [loading, setLoading]   = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [filter, setFilter]     = useState('')
  const [userFilter, setUserFilter] = useState('')
  const [lastFetch, setLastFetch] = useState(null)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const d = await adminApi.observability(filter, userFilter)
      setData(d)
      setLastFetch(new Date())
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [filter, userFilter])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 30s
  useEffect(() => {
    const t = setInterval(() => load(true), 30_000)
    return () => clearInterval(t)
  }, [load])

  const stats = data?.stats || {}
  const logs  = data?.logs  || []
  const users = data?.users || []

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-slate-100 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center">
            <Activity size={18} className="text-blue-600" />
          </div>
          <div>
            <h2 className="font-display font-semibold text-ida-navy text-sm">Observability</h2>
            <p className="text-[11px] text-slate-400">
              Query logs · Login history · User activity
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {lastFetch && (
            <span className="text-[11px] text-slate-400 flex items-center gap-1">
              <Clock size={11} />
              {relativeTime(lastFetch.toISOString())}
            </span>
          )}
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700
                       bg-slate-100 hover:bg-slate-200 rounded-lg px-3 py-1.5 transition-colors"
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-5 space-y-5">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={24} className="animate-spin text-slate-300" />
          </div>
        ) : (
          <>
            {/* Stats row */}
            <div className="grid grid-cols-4 gap-4">
              <StatCard icon={Search}     label="Queries today"    value={stats.queries_today}      color="bg-blue-500"    />
              <StatCard icon={LogIn}      label="Logins today"     value={stats.logins_today}       color="bg-emerald-500" />
              <StatCard icon={Users}      label="Active users (24h)" value={stats.active_users_today} color="bg-purple-500"  />
              <StatCard icon={TrendingUp} label="Total queries"    value={stats.total_queries}      color="bg-amber-500"   sub="all time" />
            </div>

            {/* Filters */}
            <div className="flex items-center gap-3 flex-wrap">
              {/* Action tabs */}
              <div className="flex items-center gap-1 bg-slate-100 rounded-xl p-1">
                {FILTER_TABS.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => setFilter(id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      filter === id
                        ? 'bg-white text-ida-blue shadow-sm'
                        : 'text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    <Icon size={12} />
                    {label}
                  </button>
                ))}
              </div>

              {/* User filter dropdown */}
              {users.length > 0 && (
                <div className="flex items-center gap-1.5">
                  <Filter size={12} className="text-slate-400" />
                  <select
                    value={userFilter}
                    onChange={e => setUserFilter(e.target.value)}
                    className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white text-slate-600
                               focus:ring-1 focus:ring-ida-blue focus:border-ida-blue outline-none"
                  >
                    <option value="">All users</option>
                    {users.map(u => (
                      <option key={u.id} value={u.id}>{u.email}</option>
                    ))}
                  </select>
                </div>
              )}

              <span className="ml-auto text-[11px] text-slate-400">
                {logs.length} event{logs.length !== 1 ? 's' : ''}
              </span>
            </div>

            {/* Log feed */}
            <div className="card overflow-hidden divide-y divide-slate-50">
              {logs.length === 0 ? (
                <div className="py-16 text-center text-slate-400 text-sm">
                  No activity logs yet
                </div>
              ) : (
                <AnimatePresence initial={false}>
                  {logs.map(log => <LogRow key={log.id} log={log} />)}
                </AnimatePresence>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
