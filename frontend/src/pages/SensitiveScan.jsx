import { useState, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import {
  ShieldAlert, Play, Loader2, Trash2, ChevronRight, RotateCcw, FileText, FileDown, Search, ShieldCheck,
} from 'lucide-react'
import { documents as docsApi, pii as piiApi, downloadFile } from '../api'

const TYPE_LABEL = {
  aadhaar: 'Aadhaar', pan: 'PAN', gstin: 'GSTIN', ifsc: 'IFSC',
  credit_card: 'Credit card', email: 'Email', phone_in: 'Phone',
  person: 'Name', address: 'Address',
}
const TYPE_CLS = 'bg-red-50 text-red-600 border-red-100'

export default function SensitiveScan() {
  const [docs, setDocs]         = useState([])
  const [selected, setSelected] = useState(new Set())
  const [name, setName]         = useState('')
  const [useLlm, setUseLlm]     = useState(false)
  const [running, setRunning]   = useState(false)
  const [current, setCurrent]   = useState(null)
  const [recent, setRecent]     = useState([])
  const [error, setError]       = useState('')
  const [search, setSearch]     = useState('')
  const location = useLocation()

  const loadRecent = useCallback(async () => {
    try { setRecent(await piiApi.list()) } catch { /* non-fatal */ }
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
    setCurrent(null); setSelected(new Set()); setName(''); setUseLlm(false); setError('')
  }

  async function run() {
    setError(''); setRunning(true)
    try {
      const detail = await piiApi.create({ document_ids: [...selected], name: name.trim() || null, use_llm: useLlm })
      setCurrent(detail); loadRecent()
    } catch (e) {
      setError(e.message || 'Scan failed.')
    } finally {
      setRunning(false)
    }
  }

  async function open(id) {
    setError('')
    try { setCurrent(await piiApi.get(id)) }
    catch (e) { setError(e.message || 'Could not load scan.') }
  }
  async function remove(id) {
    try { await piiApi.delete(id); if (current?.id === id) setCurrent(null); loadRecent() }
    catch (e) { setError(e.message || 'Delete failed.') }
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      <div className="flex items-center gap-3 px-6 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
          <ShieldAlert size={18} className="text-duck-blue" />
        </div>
        <div className="flex-1">
          <h2 className="font-display font-semibold text-duck-navy text-sm">Redact PII</h2>
          <p className="text-[11px] text-slate-400">Detect sensitive data and export a redacted copy — findings are stored masked only.</p>
        </div>
        {current && (
          <button onClick={resetBuilder} className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
            <RotateCcw size={13} /> New scan
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
          <ResultsView scan={current} />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3 space-y-5">
              <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Name (optional)</label>
                  <input value={name} onChange={e => setName(e.target.value)} className="input-field"
                    placeholder="Defaults to the documents scanned" />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="block text-xs font-semibold text-slate-600">Documents to scan</label>
                    <span className="text-[10px] text-slate-400">{selected.size} selected</span>
                  </div>
                  <div className="relative mb-2">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input value={search} onChange={e => setSearch(e.target.value)}
                      className="input-field pl-9" placeholder="Search documents…" />
                  </div>
                  <div className="border border-slate-200 rounded-xl divide-y divide-slate-100 max-h-72 overflow-y-auto scrollbar-thin">
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
                <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
                  <input type="checkbox" checked={useLlm} onChange={e => setUseLlm(e.target.checked)}
                    className="rounded border-slate-300 text-duck-blue focus:ring-duck-blue" />
                  Also detect names &amp; addresses with AI (slower)
                </label>
                <button onClick={run} disabled={!canRun}
                  className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                  {running ? <><Loader2 size={16} className="animate-spin" /> Scanning…</> : <><Play size={16} /> Scan for Sensitive Data</>}
                </button>
              </div>
            </div>

            <div className="lg:col-span-2">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <h3 className="font-display font-semibold text-duck-navy text-sm mb-3">Recent scans</h3>
                {recent.length === 0 && <p className="text-xs text-slate-400 py-4">No scans yet.</p>}
                <div className="space-y-1">
                  {recent.map(r => (
                    <div key={r.id} onClick={() => open(r.id)}
                      className="group flex items-center gap-2 px-3 py-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-slate-700 truncate">{r.name}</p>
                        <p className="text-[10px] text-slate-400">{r.document_count} docs · {r.finding_count} findings</p>
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

function ResultsView({ scan }) {
  const results = scan.results || []
  const counts = (scan.summary && scan.summary.counts) || {}
  const total = (scan.summary && scan.summary.total) || 0
  return (
    <div>
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h3 className="font-display font-bold text-duck-navy text-lg">{scan.name}</h3>
          <p className="text-xs text-slate-400">{results.length} docs · {total} finding{total === 1 ? '' : 's'} · {scan.status}</p>
        </div>
        <button onClick={() => downloadFile(`/pii/${scan.id}/export`, `${scan.name}.docx`)}
          className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue border border-duck-blue/30 px-3 py-2 rounded-lg hover:bg-duck-blue-pale">
          <FileDown size={14} /> Export redacted
        </button>
      </div>

      {total > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {Object.entries(counts).map(([t, n]) => (
            <span key={t} className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-1 rounded-full border ${TYPE_CLS}`}>
              {TYPE_LABEL[t] || t} · {n}
            </span>
          ))}
        </div>
      )}

      {total === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-sm text-slate-500 flex flex-col items-center gap-2">
          <ShieldCheck size={28} className="text-emerald-500" />
          No sensitive data detected in the selected documents.
        </div>
      ) : (
        <div className="space-y-4">
          {results.filter(d => (d.findings || []).length > 0).map(d => (
            <div key={d.document_id} className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100 flex items-center gap-2">
                <FileText size={14} className="text-slate-400" />
                <span className="text-sm font-medium text-duck-navy truncate">{d.filename || d.document_id}</span>
                <span className="text-[10px] text-slate-400 ml-auto">{(d.findings || []).length} findings</span>
              </div>
              <div className="divide-y divide-slate-50">
                {(d.findings || []).map((f, i) => (
                  <div key={i} className="px-4 py-2.5 flex items-start gap-3">
                    <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full border flex-shrink-0 ${TYPE_CLS}`}>
                      {TYPE_LABEL[f.type] || f.type}
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs font-mono text-slate-700">{f.masked}</p>
                      {f.snippet && <p className="text-[11px] text-slate-400 truncate">{f.snippet}</p>}
                    </div>
                    {f.page != null && <span className="text-[10px] text-slate-400 ml-auto flex-shrink-0">p.{f.page}</span>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
