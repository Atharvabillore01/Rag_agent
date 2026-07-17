import { useState, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Scale, Play, Loader2, Trash2, ChevronRight, RotateCcw, FileText, FileDown, Search,
} from 'lucide-react'
import { documents as docsApi, contentions as contentionsApi, downloadFile } from '../api'

const STANCE_STYLE = {
  admits:            { label: 'Admits',        cls: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
  denies:            { label: 'Denies',        cls: 'bg-red-50 text-red-600 border-red-100' },
  partially_admits:  { label: 'Partly admits', cls: 'bg-amber-50 text-amber-700 border-amber-100' },
  not_addressed:     { label: 'Not addressed', cls: 'bg-slate-50 text-slate-400 border-slate-100' },
}

export default function Contentions() {
  const [docs, setDocs]         = useState([])
  const [selected, setSelected] = useState(new Set())
  const [name, setName]         = useState('')
  const [running, setRunning]   = useState(false)
  const [current, setCurrent]   = useState(null)
  const [recent, setRecent]     = useState([])
  const [error, setError]       = useState('')
  const [search, setSearch]     = useState('')
  const location = useLocation()

  const loadRecent = useCallback(async () => {
    try { setRecent(await contentionsApi.list()) } catch { /* non-fatal */ }
  }, [])

  useEffect(() => {
    docsApi.list(0, 200).then(setDocs).catch(() => setError('Could not load documents.'))
    loadRecent()
  }, [loadRecent])

  // Pre-fill the name when launched from the "Compare Contentions" skill.
  useEffect(() => {
    const skill = location.state?.skill
    if (skill?.name && !name) setName(skill.name)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state])

  const readyDocs = docs.filter(d => d.status === 'ready' || d.status === 'ready_with_warnings')
  const shown = readyDocs.filter(d => d.filename.toLowerCase().includes(search.toLowerCase()))
  const canRun = selected.size >= 2 && !running

  function toggle(id) {
    setSelected(prev => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  function resetBuilder() {
    setCurrent(null); setSelected(new Set()); setName(''); setError('')
  }

  async function run() {
    setError(''); setRunning(true)
    try {
      const detail = await contentionsApi.create({
        document_ids: [...selected],
        name: name.trim() || null,
      })
      setCurrent(detail); loadRecent()
    } catch (e) {
      setError(e.message || 'Comparison failed.')
    } finally {
      setRunning(false)
    }
  }

  async function open(id) {
    setError('')
    try { setCurrent(await contentionsApi.get(id)) }
    catch (e) { setError(e.message || 'Could not load analysis.') }
  }

  async function remove(id) {
    try { await contentionsApi.delete(id); if (current?.id === id) setCurrent(null); loadRecent() }
    catch (e) { setError(e.message || 'Delete failed.') }
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
          <Scale size={18} className="text-duck-blue" />
        </div>
        <div className="flex-1">
          <h2 className="font-display font-semibold text-duck-navy text-sm">Contentions</h2>
          <p className="text-[11px] text-slate-400">Compare rival contentions across pleadings — issues derived automatically.</p>
        </div>
        {current && (
          <button onClick={resetBuilder} className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
            <RotateCcw size={13} /> New comparison
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
          <ResultsView analysis={current} />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3 space-y-5">
              <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Name (optional)</label>
                  <input value={name} onChange={e => setName(e.target.value)} className="input-field"
                    placeholder="Defaults to the pleadings compared" />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="block text-xs font-semibold text-slate-600">Pleadings to compare</label>
                    <span className="text-[10px] text-slate-400">{selected.size} selected · min 2</span>
                  </div>
                  <div className="relative mb-2">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input value={search} onChange={e => setSearch(e.target.value)}
                      className="input-field pl-9" placeholder="Search documents…" />
                  </div>
                  <div className="border border-slate-200 rounded-xl divide-y divide-slate-100 max-h-72 overflow-y-auto scrollbar-thin">
                    {shown.length === 0 && <p className="text-xs text-slate-400 p-4">No ready documents.</p>}
                    {shown.map(d => (
                      <label key={d.document_id}
                        className="flex items-center gap-3 px-3 py-2.5 hover:bg-slate-50 cursor-pointer">
                        <input type="checkbox" checked={selected.has(d.document_id)}
                          onChange={() => toggle(d.document_id)}
                          className="rounded border-slate-300 text-duck-blue focus:ring-duck-blue" />
                        <FileText size={14} className="text-slate-400 flex-shrink-0" />
                        <span className="text-xs text-slate-700 truncate">{d.filename}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <button onClick={run} disabled={!canRun}
                  className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                  {running ? <><Loader2 size={16} className="animate-spin" /> Comparing…</> : <><Play size={16} /> Compare Contentions</>}
                </button>
                {selected.size === 1 && <p className="text-xs text-amber-600">Select at least two pleadings.</p>}
              </div>
            </div>

            <div className="lg:col-span-2">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <h3 className="font-display font-semibold text-duck-navy text-sm mb-3">Recent comparisons</h3>
                {recent.length === 0 && <p className="text-xs text-slate-400 py-4">No comparisons yet.</p>}
                <div className="space-y-1">
                  {recent.map(r => (
                    <div key={r.id} onClick={() => open(r.id)}
                      className="group flex items-center gap-2 px-3 py-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-slate-700 truncate">{r.name}</p>
                        <p className="text-[10px] text-slate-400">{r.document_count} pleadings · {r.issue_count} issues</p>
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

function ResultsView({ analysis }) {
  const issues = analysis.issues || []
  const positions = analysis.results || []
  return (
    <div>
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h3 className="font-display font-bold text-duck-navy text-lg">{analysis.name}</h3>
          <p className="text-xs text-slate-400">
            {positions.length} pleadings · {issues.length} issue{issues.length === 1 ? '' : 's'} · {analysis.status}
          </p>
        </div>
        <button onClick={() => downloadFile(`/contentions/${analysis.id}/export`, `${analysis.name}.docx`)}
          className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue border border-duck-blue/30 px-3 py-2 rounded-lg hover:bg-duck-blue-pale">
          <FileDown size={14} /> Export to Word
        </button>
      </div>

      {analysis.summary && (
        <div className="bg-duck-blue-pale border border-blue-100 rounded-2xl p-4 mb-4">
          <p className="text-[10px] font-semibold text-duck-blue uppercase tracking-wider mb-1">Summary of dispute</p>
          <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{analysis.summary}</p>
        </div>
      )}

      {issues.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-sm text-slate-500">
          No distinct contentions could be identified across the selected pleadings.
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-x-auto scrollbar-thin">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-duck-navy text-white">
                <th className="text-left font-semibold px-4 py-3 min-w-[220px] sticky left-0 bg-duck-navy z-10">Issue</th>
                {positions.map(p => (
                  <th key={p.document_id} className="text-left font-semibold px-4 py-3 min-w-[220px]">
                    <span className="flex items-center gap-1.5"><FileText size={12} /> {p.filename || p.document_id}</span>
                    {p.error && (
                      <span className="block text-[10px] font-normal text-amber-300 mt-0.5">
                        ⚠ Analysis failed for this pleading — stances shown as “Not addressed”.
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {issues.map((it, i) => (
                <tr key={it.key} className={i % 2 ? 'bg-slate-50/60' : 'bg-white'}>
                  <td className="px-4 py-3 align-top sticky left-0 z-10 bg-inherit">
                    <p className="font-medium text-slate-800">{it.title}</p>
                    {it.summary && <p className="text-[11px] text-slate-400 mt-0.5">{it.summary}</p>}
                  </td>
                  {positions.map(p => {
                    const cell = (p.stances || {})[it.key] || {}
                    const st = STANCE_STYLE[cell.stance] || STANCE_STYLE.not_addressed
                    return (
                      <td key={p.document_id} className="px-4 py-3 align-top">
                        <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full border mb-1 ${st.cls}`}>{st.label}</span>
                        {cell.text && <p className="text-[11px] text-slate-600 whitespace-pre-wrap">{cell.text}</p>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
