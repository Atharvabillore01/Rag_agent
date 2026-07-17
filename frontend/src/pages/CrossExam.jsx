import { useState, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Gavel, Play, Loader2, Trash2, ChevronRight, RotateCcw, FileText, FileDown, Search,
} from 'lucide-react'
import { documents as docsApi, crossExam as crossExamApi, downloadFile } from '../api'

const TYPE_CLS = {
  foundation:    'bg-slate-50 text-slate-600 border-slate-200',
  contradiction: 'bg-amber-50 text-amber-700 border-amber-100',
  impeachment:   'bg-red-50 text-red-600 border-red-100',
  admission:     'bg-emerald-50 text-emerald-700 border-emerald-100',
}

export default function CrossExam() {
  const [docs, setDocs]           = useState([])
  const [selected, setSelected]   = useState(new Set())
  const [name, setName]           = useState('')
  const [instruction, setInstr]   = useState('')
  const [running, setRunning]     = useState(false)
  const [current, setCurrent]     = useState(null)
  const [recent, setRecent]       = useState([])
  const [error, setError]         = useState('')
  const [search, setSearch]       = useState('')
  const location = useLocation()

  const loadRecent = useCallback(async () => {
    try { setRecent(await crossExamApi.list()) } catch { /* non-fatal */ }
  }, [])

  useEffect(() => {
    docsApi.list(0, 200).then(setDocs).catch(() => setError('Could not load documents.'))
    loadRecent()
  }, [loadRecent])

  useEffect(() => {
    const skill = location.state?.skill
    if (skill?.name && !name) setName(skill.name)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state])

  const readyDocs = docs.filter(d => d.status === 'ready' || d.status === 'ready_with_warnings')
  const shown = readyDocs.filter(d => d.filename.toLowerCase().includes(search.toLowerCase()))
  const canRun = selected.size >= 1 && !running

  function toggle(id) {
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  }
  function resetBuilder() {
    setCurrent(null); setSelected(new Set()); setName(''); setInstr(''); setError('')
  }

  async function run() {
    setError(''); setRunning(true)
    try {
      const detail = await crossExamApi.create({
        document_ids: [...selected], name: name.trim() || null, instruction: instruction.trim() || null,
      })
      setCurrent(detail); loadRecent()
    } catch (e) {
      setError(e.message || 'Generation failed.')
    } finally {
      setRunning(false)
    }
  }

  async function open(id) {
    setError('')
    try { setCurrent(await crossExamApi.get(id)) }
    catch (e) { setError(e.message || 'Could not load plan.') }
  }
  async function remove(id) {
    try { await crossExamApi.delete(id); if (current?.id === id) setCurrent(null); loadRecent() }
    catch (e) { setError(e.message || 'Delete failed.') }
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      <div className="flex items-center gap-3 px-6 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
          <Gavel size={18} className="text-duck-blue" />
        </div>
        <div className="flex-1">
          <h2 className="font-display font-semibold text-duck-navy text-sm">Cross-Examination</h2>
          <p className="text-[11px] text-slate-400">Generate themed cross-examination questions from a witness statement.</p>
        </div>
        {current && (
          <button onClick={resetBuilder} className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
            <RotateCcw size={13} /> New plan
          </button>
        )}
      </div>

      {error && (
        <div className="mx-6 mt-4 flex items-center gap-2 bg-red-50 border border-red-100 rounded-xl px-4 py-2.5 text-sm text-red-600">
          <div className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />{error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto scrollbar-thin p-6">
        {current ? (
          <ResultsView plan={current} />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3 space-y-5">
              <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Name (optional)</label>
                  <input value={name} onChange={e => setName(e.target.value)} className="input-field"
                    placeholder="Defaults to the documents used" />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Case theory / focus (optional)</label>
                  <textarea value={instruction} onChange={e => setInstr(e.target.value)} rows={3}
                    className="input-field resize-none" placeholder="e.g. Establish the witness could not have seen the incident from where they claim to have stood." />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="block text-xs font-semibold text-slate-600">Source documents</label>
                    <span className="text-[10px] text-slate-400">{selected.size} selected</span>
                  </div>
                  <div className="relative mb-2">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input value={search} onChange={e => setSearch(e.target.value)}
                      className="input-field pl-9" placeholder="Search documents…" />
                  </div>
                  <div className="border border-slate-200 rounded-xl divide-y divide-slate-100 max-h-64 overflow-y-auto scrollbar-thin">
                    {shown.length === 0 && <p className="text-xs text-slate-400 p-4">No ready documents.</p>}
                    {shown.map(d => (
                      <label key={d.document_id} className="flex items-center gap-3 px-3 py-2.5 hover:bg-slate-50 cursor-pointer">
                        <input type="checkbox" checked={selected.has(d.document_id)} onChange={() => toggle(d.document_id)}
                          className="rounded border-slate-300 text-duck-blue focus:ring-duck-blue" />
                        <FileText size={14} className="text-slate-400 flex-shrink-0" />
                        <span className="text-xs text-slate-700 truncate">{d.filename}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <button onClick={run} disabled={!canRun}
                  className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                  {running ? <><Loader2 size={16} className="animate-spin" /> Generating…</> : <><Play size={16} /> Generate Questions</>}
                </button>
              </div>
            </div>

            <div className="lg:col-span-2">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <h3 className="font-display font-semibold text-duck-navy text-sm mb-3">Recent plans</h3>
                {recent.length === 0 && <p className="text-xs text-slate-400 py-4">No plans yet.</p>}
                <div className="space-y-1">
                  {recent.map(r => (
                    <div key={r.id} onClick={() => open(r.id)}
                      className="group flex items-center gap-2 px-3 py-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-slate-700 truncate">{r.name}</p>
                        <p className="text-[10px] text-slate-400">{r.document_count} docs · {r.question_count} questions</p>
                      </div>
                      <button onClick={e => { e.stopPropagation(); remove(r.id) }}
                        className="opacity-0 group-hover:opacity-100 w-6 h-6 flex items-center justify-center rounded text-red-400 hover:bg-red-50 flex-shrink-0">
                        <Trash2 size={12} />
                      </button>
                      <ChevronRight size={13} className="text-slate-300 flex-shrink-0" />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function ResultsView({ plan }) {
  const topics = plan.results || []
  const total = topics.reduce((n, t) => n + (t.questions || []).length, 0)
  return (
    <div>
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h3 className="font-display font-bold text-duck-navy text-lg">{plan.name}</h3>
          <p className="text-xs text-slate-400">{topics.length} topics · {total} question{total === 1 ? '' : 's'} · {plan.status}</p>
        </div>
        <button onClick={() => downloadFile(`/cross-exam/${plan.id}/export`, `${plan.name}.docx`)}
          className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue border border-duck-blue/30 px-3 py-2 rounded-lg hover:bg-duck-blue-pale">
          <FileDown size={14} /> Export to Word
        </button>
      </div>

      {plan.instruction && (
        <div className="bg-duck-blue-pale border border-blue-100 rounded-2xl p-4 mb-4">
          <p className="text-[10px] font-semibold text-duck-blue uppercase tracking-wider mb-1">Case theory</p>
          <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{plan.instruction}</p>
        </div>
      )}

      {total === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-sm text-slate-500">
          No questions were generated for the selected documents.
        </div>
      ) : (
        <div className="space-y-4">
          {topics.map((t, ti) => (
            <div key={ti} className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
                <Gavel size={14} className="text-duck-blue" />
                <span className="text-sm font-semibold text-duck-navy">{t.topic}</span>
                <span className="text-[10px] text-slate-400 ml-auto">{(t.questions || []).length} questions</span>
              </div>
              <ol className="divide-y divide-slate-50">
                {(t.questions || []).map((q, qi) => {
                  const cls = TYPE_CLS[q.type] || TYPE_CLS.foundation
                  return (
                    <li key={qi} className="px-4 py-3">
                      <div className="flex items-start gap-2">
                        <span className="text-xs text-slate-400 font-mono mt-0.5">{qi + 1}.</span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-slate-800">{q.question}</p>
                          <div className="flex flex-wrap items-center gap-2 mt-1.5">
                            {q.type && <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full border ${cls}`}>{q.type}</span>}
                            {q.objective && <span className="text-[11px] text-slate-500">Objective: {q.objective}</span>}
                          </div>
                          {q.basis && <p className="text-[11px] text-slate-400 mt-1">Basis: {q.basis}</p>}
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ol>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
