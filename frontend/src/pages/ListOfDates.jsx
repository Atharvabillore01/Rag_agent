import { useState, useEffect, useCallback } from 'react'
import {
  CalendarClock, Play, Loader2, Trash2, ChevronRight, RotateCcw, FileText, FileDown,
} from 'lucide-react'
import { documents as docsApi, lod as lodApi, downloadFile } from '../api'

export default function ListOfDates() {
  const [docs, setDocs]         = useState([])
  const [selected, setSelected] = useState(new Set())
  const [running, setRunning]   = useState(false)
  const [current, setCurrent]   = useState(null)
  const [recent, setRecent]     = useState([])
  const [error, setError]       = useState('')
  const [search, setSearch]     = useState('')

  const loadRecent = useCallback(async () => {
    try { setRecent(await lodApi.list()) } catch { /* non-fatal */ }
  }, [])

  useEffect(() => {
    docsApi.list(0, 200).then(setDocs).catch(() => setError('Could not load documents.'))
    loadRecent()
  }, [loadRecent])

  const readyDocs = docs.filter(d => d.status === 'ready' || d.status === 'ready_with_warnings')
  const shown = readyDocs.filter(d => d.filename.toLowerCase().includes(search.toLowerCase()))
  const canRun = selected.size > 0 && !running

  function toggle(id) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function resetBuilder() { setCurrent(null); setSelected(new Set()); setError('') }

  async function run() {
    setError(''); setRunning(true)
    try {
      const detail = await lodApi.create({ document_ids: [...selected] })
      setCurrent(detail); loadRecent()
    } catch (e) {
      setError(e.message || 'Build failed.')
    } finally {
      setRunning(false)
    }
  }

  async function open(id) {
    setError('')
    try { setCurrent(await lodApi.get(id)) }
    catch (e) { setError(e.message || 'Could not load.') }
  }

  async function remove(id) {
    try { await lodApi.delete(id); if (current?.id === id) setCurrent(null); loadRecent() }
    catch (e) { setError(e.message || 'Delete failed.') }
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
          <CalendarClock size={18} className="text-duck-blue" />
        </div>
        <div className="flex-1">
          <h2 className="font-display font-semibold text-duck-navy text-sm">List of Dates</h2>
          <p className="text-[11px] text-slate-400">Build a chronology from case documents — every date cited to its source page.</p>
        </div>
        {current && (
          <button onClick={resetBuilder} className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
            <RotateCcw size={13} /> New chronology
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
          <Timeline lod={current} />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-display font-semibold text-duck-navy text-sm">
                    Case documents <span className="text-slate-400 font-normal">({selected.size} selected)</span>
                  </h3>
                  <input value={search} onChange={e => setSearch(e.target.value)}
                    placeholder="Search…" className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 focus:border-duck-blue outline-none w-40" />
                </div>
                <div className="max-h-72 overflow-y-auto scrollbar-thin space-y-1 pr-1">
                  {shown.length === 0 && <p className="text-xs text-slate-400 py-6 text-center">No ready documents.</p>}
                  {shown.map(d => (
                    <button key={d.document_id} onClick={() => toggle(d.document_id)}
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
                <button onClick={run} disabled={!canRun}
                  className="btn-primary w-full flex items-center justify-center gap-2 mt-4 disabled:opacity-50 disabled:cursor-not-allowed">
                  {running ? <><Loader2 size={16} className="animate-spin" /> Building chronology…</> : <><Play size={16} /> Build List of Dates</>}
                </button>
              </div>
            </div>

            <div className="lg:col-span-2">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <h3 className="font-display font-semibold text-duck-navy text-sm mb-3">Recent</h3>
                {recent.length === 0 && <p className="text-xs text-slate-400 py-4">No chronologies yet.</p>}
                <div className="space-y-1">
                  {recent.map(l => (
                    <div key={l.id} onClick={() => open(l.id)}
                      className="group flex items-center gap-2 px-3 py-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-slate-700 truncate">{l.name}</p>
                        <p className="text-[10px] text-slate-400">{l.entry_count} dates · {l.document_count} docs</p>
                      </div>
                      <button onClick={e => { e.stopPropagation(); remove(l.id) }}
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

function Timeline({ lod }) {
  const rows = lod.results || []
  return (
    <div>
      <div className="mb-5 flex items-start justify-between">
        <div>
          <h3 className="font-display font-bold text-duck-navy text-lg">{lod.name}</h3>
          <p className="text-xs text-slate-400">{rows.length} date{rows.length === 1 ? '' : 's'} · {lod.status}</p>
        </div>
        <button onClick={() => downloadFile(`/lod/${lod.id}/export`, `${lod.name}.docx`)}
          className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue border border-duck-blue/30 px-3 py-2 rounded-lg hover:bg-duck-blue-pale">
          <FileDown size={14} /> Export to Word
        </button>
      </div>

      {rows.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-sm text-slate-500">
          No dated events found in the selected documents.
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <ol className="relative border-l-2 border-duck-blue-pale ml-2">
            {rows.map((r, i) => (
              <li key={i} className="mb-6 ml-6 last:mb-0">
                <span className="absolute -left-[9px] w-4 h-4 rounded-full bg-duck-blue border-2 border-white" />
                <div className="flex flex-wrap items-baseline gap-2 mb-1">
                  <span className="font-display font-bold text-duck-navy text-sm">{r.iso_date || r.date}</span>
                  {r.iso_date && r.date !== r.iso_date && (
                    <span className="text-[10px] text-slate-400">(as written: {r.date})</span>
                  )}
                </div>
                <p className="text-sm text-slate-700 mb-1">{r.event}</p>
                <p className="text-[11px] text-slate-400">
                  <FileText size={10} className="inline mr-1 -mt-0.5" />
                  {r.filename}{r.page_number ? ` · p.${r.page_number}` : ''}
                </p>
                {r.snippet && (
                  <p className="text-[11px] text-slate-400 italic mt-1 border-l-2 border-slate-100 pl-2">{r.snippet}</p>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}
