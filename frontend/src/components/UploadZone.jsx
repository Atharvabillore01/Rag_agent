import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import { UploadCloud, File, X, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { documents as docsApi } from '../api'

const ACCEPT = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/tiff': ['.tiff', '.tif'],
  'image/webp': ['.webp'],
}

function FileRow({ f, onRemove }) {
  const icons = { uploading: Loader2, done: CheckCircle2, error: AlertCircle }
  const Icon = icons[f.state] || File
  const colors = {
    idle: 'text-slate-400',
    uploading: 'text-duck-blue animate-spin-slow',
    done: 'text-emerald-500',
    error: 'text-red-500',
  }

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      className="flex items-center gap-3 px-4 py-2.5 bg-white rounded-xl border border-slate-100 shadow-card"
    >
      <Icon size={16} className={`flex-shrink-0 ${colors[f.state] || colors.idle}`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-700 truncate">{f.file.name}</p>
        <p className="text-xs text-slate-400">
          {(f.file.size / 1024 / 1024).toFixed(1)} MB
          {f.state === 'done'  && ' · Uploaded successfully'}
          {f.state === 'error' && ` · ${f.error}`}
        </p>
      </div>
      {f.state !== 'uploading' && (
        <button
          onClick={() => onRemove(f.id)}
          className="w-6 h-6 rounded-lg hover:bg-slate-100 flex items-center justify-center text-slate-400 hover:text-slate-600 transition-colors"
        >
          <X size={12} />
        </button>
      )}
    </motion.div>
  )
}

export default function UploadZone({ onUploaded }) {
  const [queue, setQueue] = useState([])

  const upload = useCallback(async (files) => {
    const items = files.map((f) => ({ id: Math.random().toString(36), file: f, state: 'idle' }))
    setQueue((q) => [...q, ...items])

    for (const item of items) {
      setQueue((q) => q.map((x) => x.id === item.id ? { ...x, state: 'uploading' } : x))
      try {
        const res = await docsApi.upload(item.file)
        setQueue((q) => q.map((x) => x.id === item.id ? { ...x, state: 'done', docId: res.document_id } : x))
        onUploaded?.()
      } catch (e) {
        setQueue((q) => q.map((x) => x.id === item.id ? { ...x, state: 'error', error: e.message } : x))
      }
    }
  }, [onUploaded])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPT,
    onDrop: upload,
    maxSize: 100 * 1024 * 1024,
  })

  const remove = (id) => setQueue((q) => q.filter((x) => x.id !== id))

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className={`relative rounded-2xl border-2 border-dashed transition-all duration-200 cursor-pointer overflow-hidden
          ${isDragActive
            ? 'border-duck-blue bg-duck-blue-pale scale-[1.01] shadow-card-h'
            : 'border-slate-200 bg-white hover:border-duck-blue hover:bg-duck-blue-pale/40'
          }`}
      >
        <input {...getInputProps()} />

        {/* Dot pattern background */}
        <div className="absolute inset-0 dot-pattern opacity-40" />

        <div className="relative flex flex-col items-center justify-center py-10 px-6 text-center">
          <motion.div
            animate={isDragActive ? { scale: [1, 1.1, 1] } : {}}
            transition={{ repeat: Infinity, duration: 1 }}
            className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-4 ${
              isDragActive ? 'bg-duck-blue text-white' : 'bg-slate-100 text-slate-400'
            }`}
          >
            <UploadCloud size={26} />
          </motion.div>

          <p className="font-semibold text-slate-700 mb-1">
            {isDragActive ? 'Drop files here' : 'Drag & drop files here'}
          </p>
          <p className="text-sm text-slate-400 mb-3">or click to browse your computer</p>

          <div className="flex flex-wrap justify-center gap-1.5">
            {['PDF', 'DOCX', 'PPTX', 'JPG', 'PNG', 'TIFF'].map((ext) => (
              <span key={ext} className="badge bg-slate-100 text-slate-500 text-[10px]">{ext}</span>
            ))}
          </div>

          <p className="text-[11px] text-slate-400 mt-3">Maximum file size: 100 MB</p>
        </div>
      </div>

      {/* File queue */}
      <AnimatePresence>
        {queue.map((f) => (
          <FileRow key={f.id} f={f} onRemove={remove} />
        ))}
      </AnimatePresence>
    </div>
  )
}
