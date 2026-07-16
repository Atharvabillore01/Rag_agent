import { useState, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  PenLine, Play, Loader2, Trash2, ChevronRight, RotateCcw, FileDown, FileText,
} from 'lucide-react'
import { documents as docsApi, drafting as draftingApi, downloadFile } from '../api'

export default function Drafting() {
  const [docs, setDocs]           = useState([])
  const [selected, setSelected]   = useState(new Set())
  const [instruction, setInstruction] = useState('')
  const [name, setName]           = useState('')
  const [running, setRunning]     = useState(false)
  const [current, setCurrent]     = useState(null)
  const [recent, setRecent]       = useState([])
  const [error, setError]         = useState('')
  const [search, setSearch]       = useState('')

  const loadRecent = useCallback(async () => {
    try { setRecent(await draftingApi.list()) } catch { /* non-fatal */ }
  }, [])

  useEffect(() => {
    docsApi.list(0, 200).then(setDocs).catch(() => setError('Could not load documents.'))
    loadRecent()
  }, [loadRecent])

  const readyDocs = docs.filter(d => d.status === 'ready' || d.status === 'ready_with_warnings')
  const shown = readyDocs.filter(d => d.filename.toLowerCase().includes(search.toLowerCase()))
  const canRun = instruction.trim().length > 0 && !running

  function toggle(id) {
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  }
  function resetBuilder() { setCurrent(null); setSelected(new Set()); setInstruction(''); setName(''); setError('') }

  async function run() {
    setError(''); setRunning(true)
    try {
      const detail = await draftingApi.create({
        instruction: instruction.trim(),
        document_ids: [...selected],
        name: name.trim() || null,
      })
      setCurrent(detail); loadRecent()
    } catch (e) {
      setError(e.message || 'Drafting failed.')
    } finally {
      setRunning(false)
    }
  }

  async function open(id) {
    setError('')
    try { setCurrent(await draftingApi.get(id)) }
    catch (e) { setError(e.message || 'Could not load draft.') }
  }
  async function remove(id) {
    try { await draftingApi.delete(id); if (current?.id === id) setCurrent(null); loadRecent() }
    catch (e) { setError(e.message || 'Delete failed.') }
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
          <PenLine size={18} className="text-duck-blue" />
        </div>
        <div className="flex-1">
          <h2 className="font-display font-semibold text-duck-navy text-sm">Drafting</h2>
          <p className="text-[11px] text-slate-400">Draft documents grounded in your files — with citations you can verify.</p>
        </div>
        {current && (
          <button onClick={resetBuilder} className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
            <RotateCcw size={13} /> New draft
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
          <div>
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="font-display font-bold text-duck-navy text-lg">{current.name}</h3>
                <p className="text-xs text-slate-400">{current.status}</p>
              </div>
              <button onClick={() => downloadFile(`/drafting/${current.id}/export`, `${current.name}.docx`)}
                className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue border border-duck-blue/30 px-3 py-2 rounded-lg hover:bg-duck-blue-pale">
                <FileDown size={14} /> Export to Word
              </button>
            </div>
            <div className="bg-white rounded-2xl border border-slate-200 p-6 prose prose-sm max-w-none text-slate-700">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{current.content || '(empty)'}</ReactMarkdown>
            </div>
            {current.citations?.length > 0 && (
              <div className="mt-4 bg-white rounded-2xl border border-slate-200 p-4">
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">Sources</p>
                <div className="flex flex-wrap gap-2">
                  {current.citations.map(c => (
                    <span key={c.number} className="inline-flex items-center gap-1.5 bg-duck-blue-pale border border-blue-100 rounded-lg px-2.5 py-1.5 text-xs text-duck-navy">
                      <span className="w-4 h-4 rounded-full bg-duck-blue text-white text-[9px] font-bold flex items-center justify-center">{c.number}</span>
                      <FileText size={11} className="text-duck-blue" />{c.filename}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3 space-y-5">
              <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">What should I draft?</label>
                  <textarea value={instruction} onChange={e => setInstruction(e.target.value)} rows={4}
                    className="input-field resize-none"
                    placeholder="e.g. Draft a formal reply on behalf of KGMI disputing the 18% interest demanded by Greenpanel." />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Name (optional)</label>
                  <input value={name} onChange={e => setName(e.target.value)} className="input-field"
                    placeholder="Defaults to the instruction" />
                </div>
                <button onClick={run} disabled={!canRun}
                  className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                  {running ? <><Loader2 size={16} className="animate-spin" /> Drafting…</> : <><Play size={16} /> Generate Draft</>}
                </button>
              </div>

              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-display font-semibold text-duck-navy text-sm">
                    Ground in documents <span className="text-slate-400 font-normal">({selected.size} selected, optional)</span>
                  </h3>
                  <input value={search} onChange={e => setSearch(e.target.value)}
                    placeholder="Search…" className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 focus:border-duck-blue outline-none w-40" />
                </div>
                <div className="max-h-56 overflow-y-auto scrollbar-thin space-y-1 pr-1">
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
              </div>
            </div>

            <div className="lg:col-span-2">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <h3 className="font-display font-semibold text-duck-navy text-sm mb-3">Recent drafts</h3>
                {recent.length === 0 && <p className="text-xs text-slate-400 py-4">No drafts yet.</p>}
                <div className="space-y-1">
                  {recent.map(r => (
                    <div key={r.id} onClick={() => open(r.id)}
                      className="group flex items-center gap-2 px-3 py-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-slate-700 truncate">{r.name}</p>
                        <p className="text-[10px] text-slate-400">{r.document_count} source docs · {r.status}</p>
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
