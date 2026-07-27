import { useState, useEffect, useCallback } from 'react'
import { UserPlus, Loader2, CalendarClock, Users } from 'lucide-react'
import { clinic as clinicApi } from '../../api'
import ClinicShell, { STATUS_DOT } from './ClinicShell'

export default function ReceptionDashboard() {
  const [doctors, setDoctors]   = useState([])
  const [queue, setQueue]       = useState([])
  const [followUps, setFollowUps] = useState([])
  const [selDoctor, setSelDoctor] = useState('')
  const [error, setError]       = useState('')
  const [addOpen, setAddOpen]   = useState(false)

  const loadDoctors = useCallback(async () => {
    try { setDoctors(await clinicApi.doctors()) } catch (e) { setError(e.message || 'Could not load doctors.') }
  }, [])
  const loadQueue = useCallback(async () => {
    try { setQueue(await clinicApi.queue(selDoctor)) } catch { /* non-fatal */ }
  }, [selDoctor])
  const loadFollowUps = useCallback(async () => {
    try { setFollowUps(await clinicApi.followUps()) } catch { /* non-fatal */ }
  }, [])

  useEffect(() => { loadDoctors(); loadFollowUps() }, [loadDoctors, loadFollowUps])
  useEffect(() => { loadQueue() }, [loadQueue])

  function onEvent(evt) {
    if (evt.type === 'queue_changed') { loadQueue(); loadDoctors() }
    if (evt.type === 'presence') loadDoctors()
  }

  return (
    <ClinicShell title="Reception" subtitle="Doctors, queue & appointments" onEvent={onEvent}>
      {error && <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-100 rounded-xl px-4 py-2.5">{error}</div>}

      <div className="flex items-center justify-between mb-4">
        <h2 className="font-display font-semibold text-duck-navy">Doctors</h2>
        <button onClick={() => setAddOpen(true)} className="btn-primary flex items-center gap-1.5 text-sm">
          <UserPlus size={15} /> Add patient
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-8">
        {doctors.map(d => (
          <button key={d.user_id} onClick={() => setSelDoctor(sel => sel === d.user_id ? '' : d.user_id)}
            className={`text-left bg-white rounded-2xl border p-4 transition-colors ${selDoctor === d.user_id ? 'border-duck-blue ring-1 ring-duck-blue' : 'border-slate-200 hover:border-slate-300'}`}>
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${STATUS_DOT[d.status] || 'bg-slate-300'}`} />
              <p className="font-medium text-duck-navy text-sm truncate">{d.display_name}</p>
            </div>
            <p className="text-[11px] text-slate-400 mt-1">{d.specialty || 'General'} · {d.status}</p>
            <p className="text-xs text-slate-600 mt-2"><Users size={12} className="inline -mt-0.5 mr-1 text-slate-400" />{d.waiting_count} waiting</p>
          </button>
        ))}
        {doctors.length === 0 && <p className="text-sm text-slate-400">No doctors yet.</p>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <h2 className="font-display font-semibold text-duck-navy mb-3">
            Queue {selDoctor && <span className="text-xs font-normal text-slate-400">· {doctors.find(d => d.user_id === selDoctor)?.display_name}</span>}
          </h2>
          <div className="bg-white rounded-2xl border border-slate-200 divide-y divide-slate-50">
            {queue.length === 0 && <p className="text-sm text-slate-400 p-6 text-center">No one waiting.</p>}
            {queue.map((q, i) => (
              <div key={q.id} className="px-4 py-3 flex items-center gap-3">
                <span className="text-xs font-mono text-slate-400 w-5">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">{q.patient_name}</p>
                  <p className="text-[11px] text-slate-400">{q.status}{q.priority > 0 ? ` · priority ${q.priority}` : ''}</p>
                </div>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${statusCls(q.status)}`}>{q.status}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="font-display font-semibold text-duck-navy mb-3">Upcoming follow-ups</h2>
          <div className="bg-white rounded-2xl border border-slate-200 divide-y divide-slate-50">
            {followUps.length === 0 && <p className="text-sm text-slate-400 p-6 text-center">None scheduled.</p>}
            {followUps.map(f => (
              <div key={f.id} className="px-4 py-3">
                <p className="text-sm font-medium text-slate-800 flex items-center gap-1.5">
                  <CalendarClock size={13} className="text-duck-blue" /> {f.patient_name}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">{new Date(f.scheduled_at).toLocaleString()}{f.reason ? ` · ${f.reason}` : ''}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {addOpen && <AddAndQueueModal doctors={doctors} onClose={() => setAddOpen(false)}
        onDone={() => { setAddOpen(false); loadQueue(); loadDoctors() }} onError={setError} />}
    </ClinicShell>
  )
}

function statusCls(s) {
  if (s === 'waiting') return 'bg-amber-50 text-amber-700 border-amber-100'
  if (s === 'in_progress') return 'bg-blue-50 text-blue-600 border-blue-100'
  if (s === 'done') return 'bg-emerald-50 text-emerald-700 border-emerald-100'
  return 'bg-slate-50 text-slate-500 border-slate-200'
}

function AddAndQueueModal({ doctors, onClose, onDone, onError }) {
  const [form, setForm] = useState({ name: '', phone: '', dob: '', complaint: '' })
  const [doctorId, setDoctorId] = useState(doctors[0]?.user_id || '')
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function submit(e) {
    e.preventDefault(); setBusy(true)
    try {
      const patient = await clinicApi.createPatient({
        name: form.name, phone: form.phone || null, dob: form.dob || null,
        details: form.complaint ? { complaint: form.complaint } : null,
      })
      if (doctorId) await clinicApi.enqueue({ patient_id: patient.id, doctor_user_id: doctorId })
      onDone()
    } catch (e2) { onError(e2.message || 'Failed.'); setBusy(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-md">
        <h3 className="font-display font-bold text-duck-navy mb-4">Add patient to queue</h3>
        <form onSubmit={submit} className="space-y-3">
          <input required value={form.name} onChange={e => set('name', e.target.value)} className="input-field" placeholder="Patient name" />
          <div className="grid grid-cols-2 gap-3">
            <input value={form.phone} onChange={e => set('phone', e.target.value)} className="input-field" placeholder="Phone" />
            <input value={form.dob} onChange={e => set('dob', e.target.value)} className="input-field" placeholder="DOB (optional)" />
          </div>
          <input value={form.complaint} onChange={e => set('complaint', e.target.value)} className="input-field" placeholder="Reason / complaint (optional)" />
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Assign to doctor</label>
            <select value={doctorId} onChange={e => setDoctorId(e.target.value)} className="input-field">
              <option value="">Do not queue yet</option>
              {doctors.map(d => <option key={d.user_id} value={d.user_id}>{d.display_name} ({d.waiting_count} waiting)</option>)}
            </select>
          </div>
          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
            <button type="submit" disabled={busy} className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50">
              {busy ? <><Loader2 size={15} className="animate-spin" /> Saving…</> : 'Add to queue'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
