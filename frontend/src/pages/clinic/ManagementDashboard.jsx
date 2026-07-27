import { useState, useEffect, useCallback } from 'react'
import { Users, Stethoscope, ClipboardList, Clock, CalendarClock, AlertTriangle, Loader2 } from 'lucide-react'
import { clinic as clinicApi, admin as adminApi } from '../../api'
import ClinicShell, { STATUS_DOT } from './ClinicShell'

export default function ManagementDashboard() {
  const [a, setA]           = useState(null)
  const [users, setUsers]   = useState([])
  const [doctors, setDoctors] = useState([])
  const [assignments, setAssignments] = useState([])
  const [error, setError]   = useState('')
  const [addDoc, setAddDoc] = useState(false)

  const load = useCallback(async () => {
    try {
      const [an, us, docs, asg] = await Promise.all([
        clinicApi.analytics(), adminApi.listUsers().catch(() => []),
        clinicApi.doctors(), clinicApi.assignments(),
      ])
      setA(an); setUsers(us); setDoctors(docs); setAssignments(asg); setError('')
    } catch (e) { setError(e.message || 'Could not load analytics.') }
  }, [])
  useEffect(() => { load() }, [load])

  function onEvent(evt) { if (evt.type === 'queue_changed' || evt.type === 'presence') load() }

  const receptions = users.filter(u => u.role === 'reception')
  const assignMap = Object.fromEntries(assignments.map(x => [x.reception_user_id, x.doctor_user_id]))

  async function setAssign(rid, doctorId) {
    try { await clinicApi.setAssignment(rid, doctorId || null); load() }
    catch (e) { setError(e.message || 'Assignment failed.') }
  }

  return (
    <ClinicShell title="Clinic management" subtitle="Analytics · doctors · reception" onEvent={onEvent}>
      {error && <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-100 rounded-xl px-4 py-2.5">{error}</div>}
      {!a ? <div className="flex items-center gap-2 text-slate-400 text-sm"><Loader2 size={16} className="animate-spin" /> Loading…</div> : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
            <Stat icon={Users} label="Patients" value={a.patients} />
            <Stat icon={Stethoscope} label="Doctors" value={a.doctors} />
            <Stat icon={ClipboardList} label="Visits" value={a.visits} />
            <Stat icon={Clock} label="Waiting" value={a.waiting_total} />
            <Stat icon={CalendarClock} label="Follow-ups" value={a.upcoming_follow_ups} />
            <Stat icon={AlertTriangle} label="Red flags" value={a.red_flag_total} danger={a.red_flag_total > 0} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-display font-semibold text-duck-navy">Doctors</h2>
                <button onClick={() => setAddDoc(true)} className="text-xs font-semibold text-duck-blue hover:underline">+ Add doctor</button>
              </div>
              <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
                <table className="w-full text-sm">
                  <tbody>
                    {a.per_doctor.map(d => (
                      <tr key={d.doctor_user_id} className="border-t border-slate-50 first:border-0">
                        <td className="px-4 py-2.5">
                          <span className="flex items-center gap-2">
                            <span className={`w-2 h-2 rounded-full ${STATUS_DOT[d.status] || 'bg-slate-300'}`} />
                            <span className="font-medium text-slate-700">{d.display_name}</span>
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-xs text-slate-500 text-right">{d.waiting} waiting</td>
                        <td className="px-3 py-2.5 text-xs text-slate-500 text-right">{d.done} done</td>
                        <td className="px-4 py-2.5 text-xs text-slate-500 text-right">{d.visits} visits</td>
                      </tr>
                    ))}
                    {a.per_doctor.length === 0 && <tr><td className="px-4 py-6 text-center text-slate-400 text-sm">No doctors yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>

            <div>
              <h2 className="font-display font-semibold text-duck-navy mb-3">Reception assignments</h2>
              <div className="bg-white rounded-2xl border border-slate-200 divide-y divide-slate-50">
                {receptions.length === 0 && <p className="text-sm text-slate-400 p-6 text-center">No receptionists.</p>}
                {receptions.map(r => (
                  <div key={r.user_id} className="px-4 py-2.5 flex items-center gap-3">
                    <span className="flex-1 text-sm text-slate-700 truncate">{r.email}</span>
                    <select value={assignMap[r.user_id] || ''} onChange={e => setAssign(r.user_id, e.target.value)} className="input-field py-1 text-xs w-40">
                      <option value="">Open (all doctors)</option>
                      {doctors.map(d => <option key={d.user_id} value={d.user_id}>{d.display_name}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <h2 className="font-display font-semibold text-duck-navy mb-3">Recent AI insights</h2>
          <div className="space-y-2">
            {a.recent_insights.filter(ri => ri.summary || ri.red_flags?.length).slice(0, 8).map((ri, i) => (
              <div key={i} className="bg-white rounded-xl border border-slate-200 p-3">
                <p className="text-xs font-medium text-slate-700">{ri.patient_name}</p>
                {ri.summary && <p className="text-xs text-slate-500 mt-0.5">{ri.summary}</p>}
                {ri.red_flags?.length > 0 && (
                  <p className="text-[11px] text-red-600 mt-1"><AlertTriangle size={11} className="inline -mt-0.5 mr-1" />{ri.red_flags.join(', ')}</p>
                )}
              </div>
            ))}
            {a.recent_insights.filter(ri => ri.summary || ri.red_flags?.length).length === 0 &&
              <p className="text-sm text-slate-400">No visit insights yet.</p>}
          </div>
        </>
      )}

      {addDoc && <AddDoctorModal users={users} onClose={() => setAddDoc(false)} onDone={() => { setAddDoc(false); load() }} onError={setError} />}
    </ClinicShell>
  )
}

function Stat({ icon: Icon, label, value, danger }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4">
      <Icon size={16} className={danger ? 'text-red-500' : 'text-duck-blue'} />
      <p className={`text-xl font-bold mt-2 leading-none ${danger ? 'text-red-600' : 'text-duck-navy'}`}>{value}</p>
      <p className="text-[11px] text-slate-400 mt-1">{label}</p>
    </div>
  )
}

function AddDoctorModal({ users, onClose, onDone, onError }) {
  const candidates = users.filter(u => u.role !== 'doctor')
  const [userId, setUserId] = useState(candidates[0]?.user_id || '')
  const [name, setName] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault(); setBusy(true)
    try {
      await clinicApi.createDoctor({ user_id: userId, display_name: name, specialty: specialty || null })
      onDone()
    } catch (e2) { onError(e2.message || 'Failed.'); setBusy(false) }
  }
  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-sm">
        <h3 className="font-display font-bold text-duck-navy mb-4">Add doctor</h3>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">User</label>
            <select value={userId} onChange={e => setUserId(e.target.value)} className="input-field" required>
              <option value="">Select a user…</option>
              {candidates.map(u => <option key={u.user_id} value={u.user_id}>{u.email}</option>)}
            </select>
          </div>
          <input required value={name} onChange={e => setName(e.target.value)} className="input-field" placeholder="Display name (e.g. Dr Rao)" />
          <input value={specialty} onChange={e => setSpecialty(e.target.value)} className="input-field" placeholder="Specialty (optional)" />
          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={busy || !userId} className="btn-primary flex-1 disabled:opacity-50">
              {busy ? 'Adding…' : 'Add doctor'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
