import { useState, useEffect, useCallback } from 'react'
import {
  Languages, Play, Loader2, Trash2, ChevronRight, RotateCcw, Copy, Check, FileDown,
} from 'lucide-react'
import { documents as docsApi, translation as translationApi, downloadFile } from '../api'

const COMMON_LANGUAGES = ['English', 'Hindi', 'Spanish', 'French', 'German', 'Arabic', 'Chinese', 'Portuguese']

export default function Translation() {
  const [docs, setDocs]       = useState([])
  const [docId, setDocId]     = useState('')
  const [language, setLang]   = useState('English')
  const [running, setRunning] = useState(false)
  const [current, setCurrent] = useState(null)
  const [recent, setRecent]   = useState([])
  const [error, setError]     = useState('')
  const [copied, setCopied]   = useState(false)

  const loadRecent = useCallback(async () => {
    try { setRecent(await translationApi.list()) } catch { /* non-fatal */ }
  }, [])

  useEffect(() => {
    docsApi.list(0, 200).then(setDocs).catch(() => setError('Could not load documents.'))
    loadRecent()
  }, [loadRecent])

  const readyDocs = docs.filter(d => d.status === 'ready' || d.status === 'ready_with_warnings')
  const canRun = docId && language.trim() && !running

  function resetBuilder() {
    setCurrent(null); setDocId(''); setLang('English'); setError('')
  }

  async function run() {
    setError(''); setRunning(true)
    try {
      const detail = await translationApi.create({ document_id: docId, target_language: language.trim() })
      setCurrent(detail); loadRecent()
    } catch (e) {
      setError(e.message || 'Translation failed.')
    } finally {
      setRunning(false)
    }
  }

  async function open(id) {
    setError('')
    try { setCurrent(await translationApi.get(id)) }
    catch (e) { setError(e.message || 'Could not load translation.') }
  }

  async function remove(id) {
    try { await translationApi.delete(id); if (current?.id === id) setCurrent(null); loadRecent() }
    catch (e) { setError(e.message || 'Delete failed.') }
  }

  function copyResult() {
    if (current?.result) {
      navigator.clipboard?.writeText(current.result)
      setCopied(true); setTimeout(() => setCopied(false), 1500)
    }
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 bg-white border-b border-slate-200 flex-shrink-0">
        <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
          <Languages size={18} className="text-duck-blue" />
        </div>
        <div className="flex-1">
          <h2 className="font-display font-semibold text-duck-navy text-sm">Translation</h2>
          <p className="text-[11px] text-slate-400">Translate a document into another language.</p>
        </div>
        {current && (
          <button onClick={resetBuilder} className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
            <RotateCcw size={13} /> New translation
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
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-display font-bold text-duck-navy text-lg">{current.filename || 'Translation'}</h3>
                <p className="text-xs text-slate-400">Translated to {current.target_language} · {current.status}</p>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={() => downloadFile(`/translation/${current.id}/export`, `${current.filename || 'translation'}.docx`)}
                  className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
                  <FileDown size={13} /> Word
                </button>
                <button onClick={copyResult}
                  className="flex items-center gap-1.5 text-xs font-semibold text-duck-blue hover:underline">
                  {copied ? <><Check size={13} /> Copied</> : <><Copy size={13} /> Copy</>}
                </button>
              </div>
            </div>
            <div className="bg-white rounded-2xl border border-slate-200 p-6 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
              {current.result || '(empty)'}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3">
              <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Document</label>
                  <select value={docId} onChange={e => setDocId(e.target.value)} className="input-field">
                    <option value="">Select a document…</option>
                    {readyDocs.map(d => (
                      <option key={d.document_id} value={d.document_id}>{d.filename}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Translate into</label>
                  <input list="dv-langs" value={language} onChange={e => setLang(e.target.value)}
                    className="input-field" placeholder="e.g. English" />
                  <datalist id="dv-langs">
                    {COMMON_LANGUAGES.map(l => <option key={l} value={l} />)}
                  </datalist>
                </div>
                <button onClick={run} disabled={!canRun}
                  className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                  {running ? <><Loader2 size={16} className="animate-spin" /> Translating…</> : <><Play size={16} /> Translate</>}
                </button>
              </div>
            </div>

            <div className="lg:col-span-2">
              <div className="bg-white rounded-2xl border border-slate-200 p-5">
                <h3 className="font-display font-semibold text-duck-navy text-sm mb-3">Recent translations</h3>
                {recent.length === 0 && <p className="text-xs text-slate-400 py-4">No translations yet.</p>}
                <div className="space-y-1">
                  {recent.map(t => (
                    <div key={t.id} onClick={() => open(t.id)}
                      className="group flex items-center gap-2 px-3 py-2.5 rounded-lg hover:bg-slate-50 cursor-pointer">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-slate-700 truncate">{t.filename || t.document_id}</p>
                        <p className="text-[10px] text-slate-400">→ {t.target_language} · {t.status}</p>
                      </div>
                      <button onClick={e => { e.stopPropagation(); remove(t.id) }}
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
