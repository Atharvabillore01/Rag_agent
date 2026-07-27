import { useState, useEffect, useCallback } from 'react'
import { Loader2, Play, Check, ArrowRightLeft, FileText, BellRing, CalendarPlus, Sparkles } from 'lucide-react'
import { clinic as clinicApi } from '../../api'
import ClinicShell from './ClinicShell'

const STATUSES = ['available', 'busy', 'away']

export default function DoctorDashboard() {
  const [status, setStatus] = useState('available')
  const [queue, setQueue]   = useState([])
  const [doctors, setDoctors] = useState([])
  const [error, setError]   = useState('')
  const [visitFor, setVisitFor] = useState(null)   // queue entry to record a visit for
  const [followFor, setFollowFor] = useState(null)

  const loadQueue = useCallback(async () => {
    try { setQueue(await clinicApi.myQueue()) } catch (e) { setError(e.message || 'Could not load queue.') }
  }, [])
  useEffect(() => {
    loadQueue()
    clinicApi.doctors().then(setDoctors).catch(() => {})
  }, [loadQueue])

  function onEvent(evt) { if (evt.type === 'queue_changed' || evt.type === 'handoff') loadQueue() }

  async function setMyStatus(s) {
    setStatus(s)
    try { await clinicApi.setStatus(s) } catch (e) { setError(e.message || 'Status update failed.') }
  }
  async function advance(id, s) {
    try { await clinicApi.updateQueue(id, s); loadQueue() } catch (e) { setError(e.message || 'Update failed.') }
  }
  async function sendIn() {
    try { await clinicApi.sendPatientIn({}) } catch (e) { setError(e.message || 'Failed.') }
  }
  async function handoff(id, doctorId) {
    if (!doctorId) return
    try { await clinicApi.handoff(id, doctorId); loadQueue() } catch (e) { setError(e.message || 'Hand-off failed.') }
  }

  return (
    <ClinicShell title="My clinic" subtitle="Your queue & visits" onEvent={onEvent}>
      {error && <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-100 rounded-xl px-4 py-2.5">{error}</div>}

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Availability</span>
        <div className="flex bg-white rounded-xl border border-slate-200 p-1">
          {STATUSES.map(s => (
            <button key={s} onClick={() => setMyStatus(s)}
              className={`text-xs font-semibold px-3 py-1.5 rounded-lg capitalize transition-colors ${status === s ? 'bg-duck-blue text-white' : 'text-slate-500 hover:text-slate-700'}`}>
              {s}
            </button>
          ))}
        </div>
        <button onClick={sendIn} className="ml-auto btn-primary flex items-center gap-1.5 text-sm">
          <BellRing size={15} /> Send in next patient
        </button>
      </div>

      <h2 className="font-display font-semibold text-duck-navy mb-3">My queue</h2>
      <div className="bg-white rounded-2xl border border-slate-200 divide-y divide-slate-50">
        {queue.length === 0 && <p className="text-sm text-slate-400 p-6 text-center">No patients waiting.</p>}
        {queue.map((q, i) => (
          <div key={q.id} className="px-4 py-3 flex flex-wrap items-center gap-3">
            <span className="text-xs font-mono text-slate-400 w-5">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-slate-800 truncate">{q.patient_name}</p>
              <p className="text-[11px] text-slate-400">{q.status}</p>
            </div>
            {q.status === 'waiting' && (
              <button onClick={() => advance(q.id, 'in_progress')} className="text-xs font-semibold text-blue-600 flex items-center gap-1 hover:underline">
                <Play size={13} /> Start
              </button>
            )}
            {q.status !== 'done' && (
              <button onClick={() => advance(q.id, 'done')} className="text-xs font-semibold text-emerald-600 flex items-center gap-1 hover:underline">
                <Check size={13} /> Done
              </button>
            )}
            <button onClick={() => setVisitFor(q)} className="text-xs font-semibold text-duck-blue flex items-center gap-1 hover:underline">
              <FileText size={13} /> Visit
            </button>
            <button onClick={() => setFollowFor(q)} className="text-xs font-semibold text-slate-500 flex items-center gap-1 hover:underline">
              <CalendarPlus size={13} /> Follow-up
            </button>
            <HandoffPicker doctors={doctors} onPick={did => handoff(q.id, did)} />
          </div>
        ))}
      </div>

      {visitFor && <VisitModal entry={visitFor} onClose={() => setVisitFor(null)} onError={setError} />}
      {followFor && <FollowUpModal entry={followFor} onClose={() => setFollowFor(null)} onError={setError} />}
    </ClinicShell>
  )
}

function HandoffPicker({ doctors, onPick }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <button onClick={() => setOpen(v => !v)} className="text-xs font-semibold text-slate-500 flex items-center gap-1 hover:underline">
        <ArrowRightLeft size={13} /> Hand off
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-48 bg-white rounded-xl border border-slate-200 shadow-elevated z-20 max-h-56 overflow-y-auto">
          {doctors.map(d => (
            <button key={d.user_id} onClick={() => { setOpen(false); onPick(d.user_id) }}
              className="w-full text-left px-3 py-2 text-xs text-slate-700 hover:bg-slate-50 truncate">{d.display_name}</button>
          ))}
        </div>
      )}
    </div>
  )
}

function VisitModal({ entry, onClose, onError }) {
  const [notes, setNotes] = useState('')
  const [busy, setBusy]   = useState(false)
  const [insights, setInsights] = useState(null)

  async function save() {
    if (!notes.trim()) return
    setBusy(true)
    try {
      const v = await clinicApi.createVisit({ patient_id: entry.patient_id, notes })
      setInsights(v.ai_insights || {})
    } catch (e) { onError(e.message || 'Save failed.') } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <h3 className="font-display font-bold text-duck-navy mb-1">Visit — {entry.patient_name}</h3>
        <p className="text-xs text-slate-400 mb-4">Type your notes; AI insights are generated on save.</p>
        {!insights ? (
          <>
            <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={6} className="input-field resize-none"
              placeholder="Symptoms, examination, assessment, plan…" />
            <div className="flex gap-2 pt-3">
              <button onClick={onClose} className="btn-ghost flex-1">Cancel</button>
              <button onClick={save} disabled={busy || !notes.trim()} className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50">
                {busy ? <><Loader2 size={15} className="animate-spin" /> Saving…</> : 'Save & analyze'}
              </button>
            </div>
          </>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-duck-blue text-sm font-semibold"><Sparkles size={15} /> AI insights</div>
            {insights.summary && <p className="text-sm text-slate-700">{insights.summary}</p>}
            <InsightList label="Symptoms" items={insights.symptoms} />
            <InsightList label="Possible conditions" items={insights.possible_conditions} />
            {insights.recommended_follow_up && <p className="text-xs text-slate-600"><b>Follow-up:</b> {insights.recommended_follow_up}</p>}
            {insights.red_flags?.length > 0 && (
              <div className="bg-red-50 border border-red-100 rounded-xl p-3">
                <p className="text-xs font-semibold text-red-600 mb-1">Red flags</p>
                <ul className="text-xs text-red-600 list-disc pl-4">{insights.red_flags.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
            )}
            <button onClick={onClose} className="btn-primary w-full">Done</button>
          </div>
        )}
      </div>
    </div>
  )
}

function InsightList({ label, items }) {
  if (!items || items.length === 0) return null
  return (
    <div>
      <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((it, i) => <span key={i} className="text-[11px] bg-slate-100 text-slate-600 rounded-full px-2 py-0.5">{it}</span>)}
      </div>
    </div>
  )
}

function FollowUpModal({ entry, onClose, onError }) {
  const [when, setWhen] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  async function save() {
    if (!when) return
    setBusy(true)
    try {
      await clinicApi.createFollowUp({ patient_id: entry.patient_id, scheduled_at: new Date(when).toISOString(), reason: reason || null })
      onClose()
    } catch (e) { onError(e.message || 'Failed.'); setBusy(false) }
  }
  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-sm">
        <h3 className="font-display font-bold text-duck-navy mb-4">Schedule follow-up — {entry.patient_name}</h3>
        <label className="block text-xs font-semibold text-slate-600 mb-1.5">Date &amp; time</label>
        <input type="datetime-local" value={when} onChange={e => setWhen(e.target.value)} className="input-field mb-3" />
        <input value={reason} onChange={e => setReason(e.target.value)} className="input-field mb-3" placeholder="Reason (optional)" />
        <div className="flex gap-2">
          <button onClick={onClose} className="btn-ghost flex-1">Cancel</button>
          <button onClick={save} disabled={busy || !when} className="btn-primary flex-1 disabled:opacity-50">
            {busy ? 'Saving…' : 'Schedule'}
          </button>
        </div>
      </div>
    </div>
  )
}
