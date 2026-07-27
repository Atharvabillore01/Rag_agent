import { useState, useEffect, useCallback } from 'react'
import { Bell, LogOut, Stethoscope } from 'lucide-react'
import { clinic as clinicApi, auth as authApi } from '../../api'
import { useAuthStore } from '../../stores/authStore'
import { useClinicEvents } from '../../hooks/useClinicEvents'

// Common clinic frame: header (role, user, notifications bell, sign out) + a live
// SSE subscription. `onEvent` lets the wrapped dashboard react to live events.
export default function ClinicShell({ title, subtitle, children, onEvent }) {
  const user = useAuthStore(s => s.user)
  const logout = useAuthStore(s => s.logout)
  const [notifs, setNotifs] = useState([])
  const [open, setOpen] = useState(false)

  const loadNotifs = useCallback(async () => {
    try { setNotifs(await clinicApi.notifications()) } catch { /* non-fatal */ }
  }, [])

  useEffect(() => { loadNotifs() }, [loadNotifs])

  useClinicEvents(evt => {
    if (evt.type === 'patient_in' || evt.type === 'patient_shared' || evt.type === 'handoff') {
      loadNotifs()
    }
    onEvent?.(evt)
  })

  async function signOut() {
    try { await authApi.logout() } catch { /* ignore */ }
    logout()
    window.location.href = '/login'
  }
  async function dismiss(id) {
    try { await clinicApi.markRead(id); setNotifs(n => n.filter(x => x.id !== id)) } catch { /* ignore */ }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center gap-3 sticky top-0 z-30">
        <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
          <Stethoscope size={18} className="text-duck-blue" />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-semibold text-duck-navy text-sm">{title}</h1>
          <p className="text-[11px] text-slate-400 truncate">{subtitle}</p>
        </div>

        <div className="relative">
          <button onClick={() => setOpen(v => !v)} className="relative w-9 h-9 rounded-lg hover:bg-slate-100 flex items-center justify-center">
            <Bell size={18} className="text-slate-500" />
            {notifs.length > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">{notifs.length}</span>
            )}
          </button>
          {open && (
            <div className="absolute right-0 mt-2 w-72 bg-white rounded-xl border border-slate-200 shadow-elevated z-40 max-h-80 overflow-y-auto">
              {notifs.length === 0 && <p className="text-xs text-slate-400 p-4 text-center">No new notifications</p>}
              {notifs.map(n => (
                <div key={n.id} className="px-3 py-2.5 border-b border-slate-50 last:border-0 flex items-start gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-700">{labelFor(n.type)}</p>
                    <p className="text-[11px] text-slate-400 truncate">{(n.payload && (n.payload.message || n.payload.patient_name)) || ''}</p>
                  </div>
                  <button onClick={() => dismiss(n.id)} className="text-[11px] text-duck-blue hover:underline flex-shrink-0">Dismiss</button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="text-right hidden sm:block">
          <p className="text-xs font-medium text-slate-700 truncate max-w-[160px]">{user?.email}</p>
          <p className="text-[10px] text-slate-400 capitalize">{user?.role}</p>
        </div>
        <button onClick={signOut} title="Sign out" className="w-9 h-9 rounded-lg hover:bg-slate-100 flex items-center justify-center text-slate-500">
          <LogOut size={17} />
        </button>
      </header>

      <main className="p-6 max-w-6xl mx-auto">{children}</main>
    </div>
  )
}

function labelFor(type) {
  if (type === 'patient_in') return 'Send in the next patient'
  if (type === 'patient_shared') return 'A patient was shared with you'
  if (type === 'handoff') return 'A patient was handed to you'
  return 'Notification'
}

export const STATUS_DOT = {
  available: 'bg-emerald-500',
  busy: 'bg-red-500',
  away: 'bg-slate-400',
}
