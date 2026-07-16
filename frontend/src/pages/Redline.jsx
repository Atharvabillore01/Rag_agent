import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  GitCompareArrows, Play, Loader2, Trash2, ChevronRight, RotateCcw, ArrowRight, FileText, FileDown,
} from 'lucide-react'
import { documents as docsApi, redline as redlineApi, downloadFile } from '../api'

const TYPE_STYLE = {
  insertion:    { label: 'Added',    cls: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
  deletion:     { label: 'Removed',  cls: 'bg-red-50 text-red-600 border-red-100' },
  modification: { label: 'Changed',  cls: 'bg-amber-50 text-amber-700 border-amber-100' },
}

export default function Redline() {
  const [docs, setDocs]         = useState([])
  const [baseId, setBaseId]     = useState('')
  const [revisedId, setRevised] = useState('')
  const [name, setName]         = useState('')
  const [running, setRunning]   = useState(false)
  const [current, setCurrent]   = useState(null)
  const [recent, setRecent]     = useState([])
  const [error, setError]       = useState('')

  const loadRecent = useCallback(async () => {
    try { setRecent(await redlineApi.list()) } catch { /* non-fatal */ }
  }, [])

  useEffect(() => {
    docsApi.list(0, 200).then(setDocs).catch(() => setError('Could not load documents.'))
    loadRecent()
  }, [loadRecent])

  const readyDocs = docs.filter(d => d.status === 'ready' || d.status === 'ready_with_warnings')
  const canRun = baseId && revisedId && baseId !== revisedId && !running

  function resetBuilder() {
    setCurrent(null); setBaseId(''); setRevised(''); setName(''); setError('')
  }

  async function run() {
    setError(''); setRunning(true)
    try {
      const detail = await redlineApi.create({
        base_document_id: baseId,
        revised_document_id: revisedId,
        name: name.trim() || null,
      })
      setCurrent(detail); loadRecent()
    } catch (e) {
      setError(e.message || 'Redline failed.')
    } finally {
      setRunning(false)
    }
  }

  async function open(id) {
    setError('')
    try { setCurrent(await redlineApi.get(id)) }
    catch (e) { setError(e.message || 'Could not load redline.') }
  }

  async function remove(id) {
    try { await redlineApi.delete(id); if (current?.id === id) setCurrent(null); loadRecent() }
    catch (e) { setError(e.message || 'Delete failed.') }
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
          <GitCompareArrows size={18} className="text-duck-blue" />
        </div>
        <div className="flex-1">
          <h2 className="font-display font-semibold text-duck-navy text-sm">Redline</h2>
          <p className="text-[11px] text-slate-400">Compare two documents — every change with its consequence.</p>
        </div>
        {current && (
          <button onClick={resetBuilder} className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
            <RotateCcw size={13} /> New redline
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
          <ResultsTable redline={current} />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3 space-y-5">
              <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_1fr] gap-3 items-end">
                  <DocSelect label="Base (original)" value={baseId} onChange={setBaseId} docs={readyDocs} exclude={revisedId} />
                  <div className="hidden sm:flex items-center justify-center pb-2.5 text-slate-300"><ArrowRight size={18} /></div>
                  <DocSelect label="Revised (new version)" value={revisedId} onChange={setRevised} docs={readyDocs} exclude={baseId} />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Name (optional)</label>
                  <input value={name} onChange={e => setName(e.target.value)} className="input-field"
                    placeholder="Defaults to “Base vs Revised”" />
                </div>
                <button onClick={run} disabled={!canRun}
                  className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                  {running ? <><Loader2 size={16} className="animate-spin" /> Comparing…</> : <><Play size={16} /> Run Redline</>}
                </button>
                {baseId && baseId === revisedId && (
                  <p className="text-xs text-amber-600">Choose two different documents.</p>
                )}
              </div>
            </div>

            <div className="lg:col-span-2">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <h3 className="font-display font-semibold text-duck-navy text-sm mb-3">Recent redlines</h3>
                {recent.length === 0 && <p className="text-xs text-slate-400 py-4">No redlines yet.</p>}
                <div className="space-y-1">
                  {recent.map(r => (
                    <div key={r.id} onClick={() => open(r.id)}
                      className="group flex items-center gap-2 px-3 py-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-slate-700 truncate">{r.name}</p>
                        <p className="text-[10px] text-slate-400">{r.change_count} changes · {r.status}</p>
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

function DocSelect({ label, value, onChange, docs, exclude }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-slate-600 mb-1.5">{label}</label>
      <select value={value} onChange={e => onChange(e.target.value)} className="input-field">
        <option value="">Select a document…</option>
        {docs.filter(d => d.document_id !== exclude).map(d => (
          <option key={d.document_id} value={d.document_id}>{d.filename}</option>
        ))}
      </select>
    </div>
  )
}

function ResultsTable({ redline }) {
  const rows = redline.results || []
  return (
    <div>
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h3 className="font-display font-bold text-duck-navy text-lg">{redline.name}</h3>
          <p className="text-xs text-slate-400">{rows.length} change{rows.length === 1 ? '' : 's'} · {redline.status}</p>
        </div>
        <button onClick={() => downloadFile(`/redline/${redline.id}/export`, `${redline.name}.docx`)}
          className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue border border-duck-blue/30 px-3 py-2 rounded-lg hover:bg-duck-blue-pale">
          <FileDown size={14} /> Export to Word
        </button>
      </div>

      {rows.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-sm text-slate-500">
          No differences found between the two documents.
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-x-auto scrollbar-thin">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-duck-navy text-white">
                <th className="text-left font-semibold px-4 py-3 w-24">Type</th>
                <th className="text-left font-semibold px-4 py-3 min-w-[280px]">Change</th>
                <th className="text-left font-semibold px-4 py-3 min-w-[280px]">Consequence</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const t = TYPE_STYLE[r.change_type] || TYPE_STYLE.modification
                return (
                  <tr key={i} className={i % 2 ? 'bg-slate-50/60' : 'bg-white'}>
                    <td className="px-4 py-3 align-top">
                      <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full border ${t.cls}`}>{t.label}</span>
                    </td>
                    <td className="px-4 py-3 align-top text-slate-700">
                      <p className="font-medium mb-1">{r.change}</p>
                      {r.before && <p className="text-[11px] text-red-500 line-through/50 whitespace-pre-wrap">− {r.before}</p>}
                      {r.after && <p className="text-[11px] text-emerald-600 whitespace-pre-wrap">+ {r.after}</p>}
                    </td>
                    <td className="px-4 py-3 align-top text-slate-600">{r.consequence}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
