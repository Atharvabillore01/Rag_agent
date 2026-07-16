import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  Table2, Plus, Trash2, X, Play, FileText, Loader2, ChevronRight, RotateCcw, FileDown,
} from 'lucide-react'
import { documents as docsApi, review as reviewApi, downloadFile } from '../api'

// Starter columns matching the demo's loan-agreement extraction.
const STARTER_QUESTIONS = [
  { header: 'Principal Amount', question: 'What is the principal loan amount?' },
  { header: 'Next Due Date',    question: 'What is the next due date of payment?' },
]

export default function ParallelReview() {
  const [docs, setDocs]                 = useState([])
  const [selected, setSelected]         = useState(new Set())
  const [questions, setQuestions]       = useState(STARTER_QUESTIONS)
  const [name, setName]                 = useState('')
  const [running, setRunning]           = useState(false)
  const [current, setCurrent]           = useState(null)   // active review detail
  const [recent, setRecent]             = useState([])
  const [error, setError]               = useState('')
  const [search, setSearch]             = useState('')
  const [addOpen, setAddOpen]           = useState(false)

  const loadRecent = useCallback(async () => {
    try { setRecent(await reviewApi.list()) } catch { /* non-fatal */ }
  }, [])

  useEffect(() => {
    docsApi.list(0, 200).then(setDocs).catch(() => setError('Could not load documents.'))
    loadRecent()
  }, [loadRecent])

  const readyDocs = docs.filter(d => d.status === 'ready' || d.status === 'ready_with_warnings')
  const shown = readyDocs.filter(d => d.filename.toLowerCase().includes(search.toLowerCase()))

  function toggleDoc(id) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function setQuestion(i, field, value) {
    setQuestions(qs => qs.map((q, idx) => idx === i ? { ...q, [field]: value } : q))
  }
  function addQuestionRow() { setQuestions(qs => [...qs, { header: '', question: '' }]) }
  function removeQuestionRow(i) { setQuestions(qs => qs.filter((_, idx) => idx !== i)) }

  function resetBuilder() {
    setCurrent(null); setSelected(new Set()); setQuestions(STARTER_QUESTIONS); setName(''); setError('')
  }

  const validQuestions = questions.filter(q => q.header.trim() && q.question.trim())
  const canRun = name.trim() && selected.size > 0 && validQuestions.length > 0 && !running

  async function runReview() {
    setError(''); setRunning(true)
    try {
      const detail = await reviewApi.create({
        name: name.trim(),
        document_ids: [...selected],
        questions: validQuestions.map(q => ({ header: q.header.trim(), question: q.question.trim() })),
      })
      setCurrent(detail)
      loadRecent()
    } catch (e) {
      setError(e.message || 'Review failed.')
    } finally {
      setRunning(false)
    }
  }

  async function openReview(id) {
    setError('')
    try { setCurrent(await reviewApi.get(id)) }
    catch (e) { setError(e.message || 'Could not load review.') }
  }

  async function deleteReview(id) {
    try {
      await reviewApi.delete(id)
      if (current?.id === id) setCurrent(null)
      loadRecent()
    } catch (e) { setError(e.message || 'Delete failed.') }
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
          <Table2 size={18} className="text-duck-blue" />
        </div>
        <div className="flex-1">
          <h2 className="font-display font-semibold text-duck-navy text-sm">Parallel Review</h2>
          <p className="text-[11px] text-slate-400">Ask the same questions across many documents — answered only from those documents.</p>
        </div>
        {current && (
          <button onClick={resetBuilder}
            className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
            <RotateCcw size={13} /> New review
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
          <ResultsTable review={current} onAddColumn={() => setAddOpen(true)} />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            {/* Builder */}
            <div className="lg:col-span-3 space-y-5">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">Review name</label>
                <input value={name} onChange={e => setName(e.target.value)} className="input-field"
                  placeholder="e.g. Loan Terms & Covenants Review" />
              </div>

              {/* Documents */}
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-display font-semibold text-duck-navy text-sm">
                    Documents <span className="text-slate-400 font-normal">({selected.size} selected)</span>
                  </h3>
                  <input value={search} onChange={e => setSearch(e.target.value)}
                    placeholder="Search…" className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 focus:border-duck-blue outline-none w-40" />
                </div>
                <div className="max-h-64 overflow-y-auto scrollbar-thin space-y-1 pr-1">
                  {shown.length === 0 && (
                    <p className="text-xs text-slate-400 py-6 text-center">No ready documents. Upload and process files first.</p>
                  )}
                  {shown.map(d => (
                    <button key={d.document_id} onClick={() => toggleDoc(d.document_id)}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-colors ${
                        selected.has(d.document_id) ? 'bg-duck-blue-pale' : 'hover:bg-slate-50'
                      }`}>
                      <span className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
                        selected.has(d.document_id) ? 'bg-duck-blue border-duck-blue' : 'border-slate-300'
                      }`}>
                        {selected.has(d.document_id) && <span className="text-white text-[9px]">✓</span>}
                      </span>
                      <FileText size={13} className="text-slate-400 flex-shrink-0" />
                      <span className="text-xs text-slate-700 truncate">{d.filename}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Questions */}
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <h3 className="font-display font-semibold text-duck-navy text-sm mb-3">Questions (columns)</h3>
                <div className="space-y-2.5">
                  {questions.map((q, i) => (
                    <div key={i} className="flex gap-2 items-start">
                      <input value={q.header} onChange={e => setQuestion(i, 'header', e.target.value)}
                        placeholder="Column header" className="input-field w-40 flex-shrink-0 text-sm" />
                      <input value={q.question} onChange={e => setQuestion(i, 'question', e.target.value)}
                        placeholder="Question to ask each document" className="input-field flex-1 text-sm" />
                      <button onClick={() => removeQuestionRow(i)}
                        className="w-9 h-9 flex items-center justify-center rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 flex-shrink-0">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
                <button onClick={addQuestionRow}
                  className="mt-3 flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
                  <Plus size={14} /> Add question
                </button>
              </div>

              <button onClick={runReview} disabled={!canRun}
                className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                {running
                  ? <><Loader2 size={16} className="animate-spin" /> Running review…</>
                  : <><Play size={16} /> Run Review</>}
              </button>
            </div>

            {/* Recent */}
            <div className="lg:col-span-2">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <h3 className="font-display font-semibold text-duck-navy text-sm mb-3">Recent reviews</h3>
                {recent.length === 0 && <p className="text-xs text-slate-400 py-4">No reviews yet.</p>}
                <div className="space-y-1">
                  {recent.map(r => (
                    <div key={r.id}
                      className="group flex items-center gap-2 px-3 py-2.5 rounded-lg hover:bg-slate-50 cursor-pointer"
                      onClick={() => openReview(r.id)}>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-slate-700 truncate">{r.name}</p>
                        <p className="text-[10px] text-slate-400">
                          {r.document_count} docs · {r.question_count} questions · {r.status}
                        </p>
                      </div>
                      <button onClick={e => { e.stopPropagation(); deleteReview(r.id) }}
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

      {addOpen && current && (
        <AddColumnModal
          onClose={() => setAddOpen(false)}
          onSubmit={async (cols) => {
            setError('')
            try {
              const updated = await reviewApi.addColumns(current.id, { questions: cols })
              setCurrent(updated); setAddOpen(false)
            } catch (e) { setError(e.message || 'Add column failed.') }
          }}
        />
      )}
    </div>
  )
}

function ResultsTable({ review, onAddColumn }) {
  const cols = review.questions || []
  const results = review.results || {}
  const rows = (review.document_ids || []).map(id => ({ id, ...(results[id] || {}) }))

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-display font-bold text-duck-navy text-lg">{review.name}</h3>
          <p className="text-xs text-slate-400">{rows.length} documents · {cols.length} columns · {review.status}</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => downloadFile(`/review/${review.id}/export`, `${review.name}.docx`)}
            className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue border border-duck-blue/30 px-3 py-2 rounded-lg hover:bg-duck-blue-pale">
            <FileDown size={14} /> Export to Word
          </button>
          <button onClick={onAddColumn}
            className="flex items-center gap-1.5 text-xs font-semibold text-white bg-duck-blue px-3 py-2 rounded-lg hover:bg-duck-blue-hover">
            <Plus size={14} /> Add column
          </button>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-x-auto scrollbar-thin">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-duck-navy text-white">
              <th className="text-left font-semibold px-4 py-3 sticky left-0 bg-duck-navy min-w-[220px]">Document</th>
              {cols.map(c => (
                <th key={c.key} className="text-left font-semibold px-4 py-3 min-w-[180px]">{c.header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={row.id} className={ri % 2 ? 'bg-slate-50/60' : 'bg-white'}>
                <td className="px-4 py-3 sticky left-0 bg-inherit font-medium text-slate-700 align-top">
                  <div className="flex items-center gap-2">
                    <FileText size={13} className="text-slate-400 flex-shrink-0" />
                    <span className="truncate max-w-[200px]">{row.filename || row.id}</span>
                  </div>
                  {row.error && <p className="text-[10px] text-red-500 mt-1">error: {row.error}</p>}
                  {row.truncated && <p className="text-[10px] text-amber-600 mt-1">document truncated for length</p>}
                </td>
                {cols.map(c => (
                  <td key={c.key} className="px-4 py-3 text-slate-600 align-top">
                    {row.answers?.[c.key] ?? '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AddColumnModal({ onClose, onSubmit }) {
  const [header, setHeader] = useState('')
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!header.trim() || !question.trim()) return
    setBusy(true)
    await onSubmit([{ header: header.trim(), question: question.trim() }])
    setBusy(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
        className="bg-white rounded-2xl shadow-elevated w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display font-bold text-duck-navy">Add column</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        <label className="block text-xs font-semibold text-slate-600 mb-1.5">Column header</label>
        <input value={header} onChange={e => setHeader(e.target.value)} className="input-field mb-3" placeholder="e.g. Tenure" />
        <label className="block text-xs font-semibold text-slate-600 mb-1.5">Question</label>
        <input value={question} onChange={e => setQuestion(e.target.value)} className="input-field mb-5" placeholder="e.g. What is the loan tenure?" />
        <button onClick={submit} disabled={busy || !header.trim() || !question.trim()}
          className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50">
          {busy ? <><Loader2 size={16} className="animate-spin" /> Adding…</> : <>Add column</>}
        </button>
      </motion.div>
    </div>
  )
}
