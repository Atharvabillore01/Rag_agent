import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText, Settings, LogOut, ChevronRight,
  Plus, Trash2, MessagesSquare, X, Activity, Table2, GitCompareArrows, Languages, CalendarClock, PenLine, Scale, ShieldAlert, Gavel, ClipboardCheck, Building2,
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
import { auth as authApi } from '../api'
import DuckVaultLogo from './DuckVaultLogo'

const NAV = [
  { to: '/documents', icon: FileText, label: 'Documents',       sub: 'Manage files' },
  { to: '/review',    icon: Table2,           label: 'Parallel Review', sub: 'Compare documents' },
  { to: '/redline',   icon: GitCompareArrows, label: 'Redline',         sub: 'Diff two documents' },
  { to: '/translation', icon: Languages,      label: 'Translation',     sub: 'Translate a document' },
  { to: '/lod',         icon: CalendarClock,  label: 'List of Dates',   sub: 'Build a chronology' },
  { to: '/contentions', icon: Scale,          label: 'Contentions',     sub: 'Compare pleadings' },
  { to: '/cross-exam',  icon: Gavel,          label: 'Cross-Exam',      sub: 'Question a witness' },
  { to: '/playbook',    icon: ClipboardCheck, label: 'Playbook',        sub: 'Contract clause review' },
  { to: '/sensitive',   icon: ShieldAlert,    label: 'Redact PII',      sub: 'Find & redact sensitive data' },
  { to: '/drafting',    icon: PenLine,        label: 'Drafting',        sub: 'Draft from documents' },
]

const ROLE_LABELS = {
  org_admin: 'Admin',
  editor:    'Editor',
  viewer:    'Viewer',
  demo:      'Demo',
}

export default function Sidebar({ onClose }) {
  const { user, logout } = useAuthStore()
  const navigate          = useNavigate()
  const location          = useLocation()

  const { sortedSessions, currentSessionId, newSession, switchSession, deleteSession } = useChatStore()
  const sessions = sortedSessions()

  const isAdmin  = user?.role === 'org_admin'
  const isPlatformAdmin = user?.is_platform_admin === true
  const initials = user?.email ? user.email.slice(0, 2).toUpperCase() : 'U'

  async function handleLogout() {
    try { await authApi.logout() } catch { /* best-effort revoke */ }
    logout(); navigate('/login')
  }

  function handleNewChat() {
    newSession(); navigate('/chat'); onClose?.()
  }

  function handleSwitchSession(id) {
    switchSession(id); navigate('/chat'); onClose?.()
  }

  return (
    <aside
      className="w-64 flex-shrink-0 flex flex-col h-screen overflow-hidden bg-white"
      style={{ borderRight: '1px solid #e2e8f0' }}
    >
      {/* ── Logo header ── */}
      <div className="px-4 pt-5 pb-4 flex items-center justify-between"
           style={{ borderBottom: '1px solid #f1f5f9' }}>
        <button
          onClick={() => { navigate('/chat'); onClose?.() }}
          className="hover:opacity-80 transition-opacity"
        >
          <DuckVaultLogo size="sm" />
        </button>
        <button
          onClick={onClose}
          className="md:hidden w-8 h-8 flex items-center justify-center rounded-lg
                     text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      {/* ── Scrollable body ── */}
      <div className="flex-1 flex flex-col overflow-hidden px-3 pt-3">

        {/* New Chat */}
        <motion.button
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.97 }}
          onClick={handleNewChat}
          className="w-full flex items-center gap-2.5 px-4 py-2.5 mb-4 rounded-xl
                     text-white text-sm font-semibold transition-colors
                     shadow-[0_2px_14px_rgba(224,93,13,0.30)]"
          style={{ background: 'linear-gradient(135deg,#E05D0D 0%,#C54F0A 100%)' }}
        >
          <Plus size={15} />
          New Chat
        </motion.button>

        <div className="flex-1 overflow-y-auto scrollbar-thin pr-0.5 space-y-0.5">

          {/* Chat history */}
          {sessions.length > 0 && (
            <div className="mb-2">
              <p className="px-2 mb-1.5 mt-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                Recent Chats
              </p>
              <AnimatePresence initial={false}>
                {sessions.map(sess => {
                  const isActive = sess.id === currentSessionId && location.pathname === '/chat'
                  return (
                    <motion.div
                      key={sess.id}
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -6 }}
                      className="group flex items-center gap-2 px-2.5 py-2 rounded-xl mb-0.5
                                 cursor-pointer transition-all duration-150"
                      style={{
                        background: isActive ? '#eff6ff' : 'transparent',
                        color: isActive ? '#1d4ed8' : '#64748b',
                      }}
                      onMouseEnter={e => !isActive && (e.currentTarget.style.background = '#f8fafc')}
                      onMouseLeave={e => !isActive && (e.currentTarget.style.background = 'transparent')}
                      onClick={() => handleSwitchSession(sess.id)}
                    >
                      <MessagesSquare size={13} style={{ opacity: isActive ? 1 : 0.5 }} />
                      <span className="flex-1 truncate text-xs leading-tight font-medium">
                        {sess.title || 'New Chat'}
                      </span>
                      <button
                        onClick={e => { e.stopPropagation(); deleteSession(sess.id) }}
                        className="opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center
                                   rounded transition-all flex-shrink-0 text-red-400 hover:bg-red-50"
                      >
                        <Trash2 size={11} />
                      </button>
                    </motion.div>
                  )
                })}
              </AnimatePresence>
            </div>
          )}

          {/* Navigation */}
          <div className="mb-2">
            <p className="px-2 mb-1.5 mt-2 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
              Navigation
            </p>
            {NAV.map(({ to, icon: Icon, label, sub }) => (
              <NavLink key={to} to={to} onClick={() => onClose?.()}>
                {({ isActive }) => (
                  <motion.div
                    whileHover={{ x: 2 }}
                    transition={{ duration: 0.12 }}
                    className="flex items-center gap-3 px-2.5 py-2.5 rounded-xl mb-0.5 cursor-pointer transition-all"
                    style={{
                      background: isActive ? '#eff6ff' : 'transparent',
                      color: isActive ? '#1d4ed8' : '#475569',
                    }}
                  >
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                         style={{ background: isActive ? '#dbeafe' : '#f1f5f9' }}>
                      <Icon size={15} style={{ color: isActive ? '#1d4ed8' : '#64748b' }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate leading-none mb-0.5">{label}</p>
                      <p className="text-[11px] truncate text-slate-400">{sub}</p>
                    </div>
                    {isActive && <ChevronRight size={13} className="text-blue-500 opacity-60" />}
                  </motion.div>
                )}
              </NavLink>
            ))}
          </div>

          {/* Admin */}
          {isAdmin && (
            <div>
              <p className="px-2 mb-1.5 mt-2 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                Administration
              </p>
              {[
                { to: '/admin',         icon: Settings,  label: 'Admin Panel',   sub: 'Users & config'  },
                { to: '/observability', icon: Activity,  label: 'Observability', sub: 'Logs & activity' },
              ].map(({ to, icon: Icon, label, sub }) => (
                <NavLink key={to} to={to} onClick={() => onClose?.()}>
                  {({ isActive }) => (
                    <motion.div
                      whileHover={{ x: 2 }}
                      transition={{ duration: 0.12 }}
                      className="flex items-center gap-3 px-2.5 py-2.5 rounded-xl mb-0.5 cursor-pointer transition-all"
                      style={{
                        background: isActive ? '#eff6ff' : 'transparent',
                        color: isActive ? '#1d4ed8' : '#475569',
                      }}
                    >
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                           style={{ background: isActive ? '#dbeafe' : '#f1f5f9' }}>
                        <Icon size={15} style={{ color: isActive ? '#1d4ed8' : '#64748b' }} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate leading-none mb-0.5">{label}</p>
                        <p className="text-[11px] truncate text-slate-400">{sub}</p>
                      </div>
                      {isActive && <ChevronRight size={13} className="text-blue-500 opacity-60" />}
                    </motion.div>
                  )}
                </NavLink>
              ))}
            </div>
          )}

          {/* Platform (super-admin) — cross-tenant management */}
          {isPlatformAdmin && (
            <div>
              <p className="px-2 mb-1.5 mt-2 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                Platform
              </p>
              <NavLink to="/platform" onClick={() => onClose?.()}>
                {({ isActive }) => (
                  <motion.div
                    whileHover={{ x: 2 }}
                    transition={{ duration: 0.12 }}
                    className="flex items-center gap-3 px-2.5 py-2.5 rounded-xl mb-0.5 cursor-pointer transition-all"
                    style={{
                      background: isActive ? '#eff6ff' : 'transparent',
                      color: isActive ? '#1d4ed8' : '#475569',
                    }}
                  >
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                         style={{ background: isActive ? '#dbeafe' : '#f1f5f9' }}>
                      <Building2 size={15} style={{ color: isActive ? '#1d4ed8' : '#64748b' }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate leading-none mb-0.5">Platform Console</p>
                      <p className="text-[11px] truncate text-slate-400">All organizations</p>
                    </div>
                    {isActive && <ChevronRight size={13} className="text-blue-500 opacity-60" />}
                  </motion.div>
                )}
              </NavLink>
            </div>
          )}
        </div>
      </div>

      {/* ── User footer ── */}
      <div className="px-3 pb-4 pt-3 flex-shrink-0"
           style={{ borderTop: '1px solid #f1f5f9' }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
               style={{ background: 'linear-gradient(135deg,#E05D0D,#C54F0A)', boxShadow: '0 2px 8px rgba(224,93,13,0.3)' }}>
            <span className="text-white text-xs font-bold">{initials}</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-slate-700 truncate">
              {user?.email?.split('@')[0] || 'User'}
            </p>
            <p className="text-[10px] text-slate-400">
              {ROLE_LABELS[user?.role] || 'Viewer'}
            </p>
          </div>
          <button
            onClick={handleLogout}
            title="Logout"
            className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors
                       text-slate-400 hover:text-red-500 hover:bg-red-50"
          >
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </aside>
  )
}
