import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText, FileImage, Presentation, File,
  Trash2, RefreshCw, CheckCircle2, AlertCircle,
  Clock, Loader2, Plus, X, Upload,
} from 'lucide-react'
import { documents as docsApi } from '../api'
import { useAuthStore } from '../stores/authStore'
import UploadZone from '../components/UploadZone'

const STATUS_CONFIG = {
  ready:               { label: 'Ready',        color: 'bg-emerald-50 text-emerald-700 border-emerald-100', dot: 'bg-emerald-400' },
  ready_with_warnings: { label: 'Ready',         color: 'bg-amber-50 text-amber-700 border-amber-100',       dot: 'bg-amber-400'   },
  uploading:           { label: 'Uploading',     color: 'bg-blue-50 text-blue-600 border-blue-100',           dot: 'bg-blue-400 animate-pulse' },
  scanning:            { label: 'Scanning',      color: 'bg-blue-50 text-blue-600 border-blue-100',           dot: 'bg-blue-400 animate-pulse' },
  parsing:             { label: 'Parsing',       color: 'bg-blue-50 text-blue-600 border-blue-100',           dot: 'bg-blue-400 animate-pulse' },
  chunking:            { label: 'Chunking',      color: 'bg-blue-50 text-blue-600 border-blue-100',           dot: 'bg-blue-400 animate-pulse' },
  embedding:           { label: 'Embedding',     color: 'bg-purple-50 text-purple-700 border-purple-100',     dot: 'bg-purple-400 animate-pulse' },
  indexing:            { label: 'Indexing',      color: 'bg-purple-50 text-purple-700 border-purple-100',     dot: 'bg-purple-400 animate-pulse' },
  failed_retryable:    { label: 'Failed',        color: 'bg-red-50 text-red-700 border-red-100',              dot: 'bg-red-400' },
  failed_terminal:     { label: 'Failed',        color: 'bg-red-50 text-red-700 border-red-100',              dot: 'bg-red-400' },
  rejected_security:   { label: 'Rejected',      color: 'bg-red-50 text-red-700 border-red-100',              dot: 'bg-red-400' },
}

const FILE_ICONS = {
  pdf:   { icon: FileText,     color: 'text-red-500',    bg: 'bg-red-50'    },
  docx:  { icon: FileText,     color: 'text-blue-500',   bg: 'bg-blue-50'   },
  pptx:  { icon: Presentation, color: 'text-orange-500', bg: 'bg-orange-50' },
  image: { icon: FileImage,    color: 'text-purple-500', bg: 'bg-purple-50' },
}

function getFileConfig(type) {
  return FILE_ICONS[type] || { icon: File, color: 'text-slate-500', bg: 'bg-slate-50' }
}

function isProcessing(status) {
  return !['ready','ready_with_warnings','failed_retryable','failed_terminal','rejected_security'].includes(status)
}

function DocCard({ doc, onDelete }) {
  const [deleting, setDeleting] = useState(false)
  const sc = STATUS_CONFIG[doc.status] || { label: doc.status, color: 'bg-slate-50 text-slate-600 border-slate-100', dot: 'bg-slate-400' }
  const fc = getFileConfig(doc.file_type)
  const Icon = fc.icon
  const processing = isProcessing(doc.status)

  async function handleDelete() {
    if (!confirm(`Delete "${doc.filename}"? This cannot be undone.`)) return
    setDeleting(true)
    try { await docsApi.delete(doc.document_id); onDelete(doc.document_id) }
    catch (e) { alert(e.message); setDeleting(false) }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="card-hover p-4 flex flex-col gap-3"
    >
      {/* Top row */}
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-xl ${fc.bg} flex items-center justify-center flex-shrink-0`}>
          {processing
            ? <Loader2 size={18} className="text-ida-blue animate-spin-slow" />
            : <Icon size={18} className={fc.color} />
          }
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-700 truncate" title={doc.filename}>
            {doc.filename}
          </p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            {doc.file_type?.toUpperCase()} · {doc.page_count ? `${doc.page_count} pages` : 'Processing…'}
          </p>
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="w-7 h-7 rounded-lg hover:bg-red-50 flex items-center justify-center text-slate-300 hover:text-red-400 transition-colors flex-shrink-0"
          title="Delete document"
        >
          {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
        </button>
      </div>

      {/* Status & date */}
      <div className="flex items-center justify-between">
        <span className={`badge border text-[10px] ${sc.color}`}>
          <span className={`status-dot flex-shrink-0 ${sc.dot}`} />
          {sc.label}
        </span>
        <p className="text-[10px] text-slate-400">
          {new Date(doc.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
        </p>
      </div>
    </motion.div>
  )
}

export default function Documents() {
  const [docs, setDocs]         = useState([])
  const [loading, setLoading]   = useState(true)
  const [showUpload, setShowUpload] = useState(false)
  const user = useAuthStore((s) => s.user)
  const canUpload = ['org_admin', 'editor'].includes(user?.role)

  const fetchDocs = useCallback(async () => {
    setLoading(true)
    try { setDocs(await docsApi.list()) }
    catch {}
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchDocs() }, [fetchDocs])

  // Poll for processing docs
  useEffect(() => {
    const processing = docs.some((d) => isProcessing(d.status))
    if (!processing) return
    const timer = setInterval(fetchDocs, 4000)
    return () => clearInterval(timer)
  }, [docs, fetchDocs])

  function removeDoc(id) { setDocs((d) => d.filter((x) => x.document_id !== id)) }

  const ready = docs.filter((d) => d.status === 'ready' || d.status === 'ready_with_warnings').length
  const processing = docs.filter((d) => isProcessing(d.status)).length

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-slate-100 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-ida-saffron-lt flex items-center justify-center">
            <FileText size={18} className="text-ida-saffron" />
          </div>
          <div>
            <h2 className="font-display font-semibold text-ida-navy text-sm">Document Library</h2>
            <p className="text-[11px] text-slate-400">
              {loading ? 'Loading…' : `${docs.length} document${docs.length !== 1 ? 's' : ''} · ${ready} ready`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={fetchDocs} className="btn-ghost flex items-center gap-1.5 text-xs py-2">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
          {canUpload && (
            <button onClick={() => setShowUpload((v) => !v)} className="btn-primary flex items-center gap-1.5 text-sm py-2.5">
              {showUpload ? <X size={14} /> : <Plus size={14} />}
              {showUpload ? 'Close' : 'Upload'}
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-6">
        {/* Stats bar */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          {[
            { label: 'Total Documents', value: docs.length, icon: FileText,      color: 'text-ida-blue',    bg: 'bg-ida-blue-pale' },
            { label: 'Ready to Query',  value: ready,       icon: CheckCircle2,  color: 'text-emerald-600', bg: 'bg-emerald-50'    },
            { label: 'Processing',      value: processing,  icon: Clock,         color: 'text-amber-600',   bg: 'bg-amber-50'      },
          ].map(({ label, value, icon: Icon, color, bg }) => (
            <div key={label} className="card p-4 flex items-center gap-3">
              <div className={`w-10 h-10 rounded-xl ${bg} flex items-center justify-center`}>
                <Icon size={18} className={color} />
              </div>
              <div>
                <p className="text-lg font-display font-bold text-slate-800">{value}</p>
                <p className="text-[11px] text-slate-500">{label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Upload zone */}
        <AnimatePresence>
          {showUpload && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-6 overflow-hidden"
            >
              <div className="card p-5">
                <div className="flex items-center gap-2 mb-4">
                  <Upload size={15} className="text-ida-saffron" />
                  <h3 className="font-display font-semibold text-sm text-slate-700">Upload Documents</h3>
                </div>
                <UploadZone onUploaded={() => { setTimeout(fetchDocs, 1500) }} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Document grid */}
        {loading && !docs.length ? (
          <div className="flex items-center justify-center py-24">
            <div className="text-center">
              <div className="w-12 h-12 border-2 border-slate-200 border-t-ida-blue rounded-full animate-spin mx-auto mb-4" />
              <p className="text-slate-500 text-sm">Loading documents…</p>
            </div>
          </div>
        ) : !docs.length ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
              <FileText size={28} className="text-slate-300" />
            </div>
            <p className="font-display font-semibold text-slate-600 mb-1">No documents yet</p>
            <p className="text-sm text-slate-400 mb-5">Upload PDFs, Word documents, or presentations to get started</p>
            {canUpload && (
              <button onClick={() => setShowUpload(true)} className="btn-primary flex items-center gap-2 text-sm">
                <Upload size={14} /> Upload First Document
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            <AnimatePresence>
              {docs.map((doc) => (
                <DocCard key={doc.document_id} doc={doc} onDelete={removeDoc} />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  )
}
