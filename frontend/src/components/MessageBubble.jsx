import { useState } from 'react'
import { motion } from 'framer-motion'
import { FileText, AlertCircle, ExternalLink, Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { documents as docsApi } from '../api'

function CitationChip({ citation, index }) {
  const [loading, setLoading] = useState(false)

  async function handleOpen() {
    if (!citation.document_id || loading) return
    setLoading(true)
    try {
      const { url, file_type } = await docsApi.viewUrl(citation.document_id)
      const page = citation.page_number
      // PDF viewers (Chrome, Firefox) support #page=N fragment
      const fragment = (page && file_type === 'pdf') ? `#page=${page}` : ''
      window.open(url + fragment, '_blank', 'noopener,noreferrer')
    } catch {
      // If presigned URL fails, silently ignore
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.button
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      onClick={handleOpen}
      disabled={loading}
      className="inline-flex items-center gap-1.5 bg-ida-blue-pale border border-blue-100 rounded-lg
                 px-2.5 py-1.5 text-xs cursor-pointer hover:bg-blue-50 hover:border-ida-blue/30
                 hover:shadow-sm transition-all disabled:opacity-60 disabled:cursor-wait"
    >
      <span className="w-4 h-4 rounded-full bg-ida-blue text-white text-[9px] font-bold flex items-center justify-center flex-shrink-0">
        {index + 1}
      </span>
      {loading
        ? <Loader2 size={11} className="text-ida-blue animate-spin flex-shrink-0" />
        : <FileText size={11} className="text-ida-blue flex-shrink-0" />
      }
      <span className="text-ida-navy font-medium truncate max-w-[120px]">
        {citation.section_heading || `Page ${citation.page_number || '?'}`}
      </span>
      {citation.page_number && (
        <span className="text-slate-400 font-normal">p.{citation.page_number}</span>
      )}
      <ExternalLink size={9} className="text-slate-300 flex-shrink-0 ml-0.5" />
    </motion.button>
  )
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-1 py-2">
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </div>
  )
}

export default function MessageBubble({ message }) {
  const isUser      = message.role === 'user'
  const isError     = message.status === 'error'
  const isStreaming = message.status === 'streaming'
  const isEmpty     = isStreaming && !message.text

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`flex gap-3 px-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold mt-0.5 ${
        isUser
          ? 'bg-ida-grad text-white'
          : 'bg-white border-2 border-slate-100 shadow-card overflow-hidden'
      }`}>
        {isUser ? (
          'U'
        ) : (
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="10" fill="#0D2545"/>
            <rect x="4" y="13" width="3" height="5" fill="white" opacity="0.7" rx="0.5"/>
            <rect x="8" y="10" width="4" height="8" fill="white" opacity="0.9" rx="0.5"/>
            <rect x="13" y="12" width="3" height="6" fill="white" opacity="0.8" rx="0.5"/>
            <rect x="4" y="17" width="12" height="1.5" fill="#E05D0D" opacity="0.9"/>
          </svg>
        )}
      </div>

      {/* Bubble */}
      <div className={`max-w-[72%] ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-2`}>
        <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-ida-grad text-white rounded-tr-sm'
            : isError
              ? 'bg-red-50 border border-red-100 text-red-700 rounded-tl-sm'
              : 'bg-white shadow-card border border-slate-100 text-slate-800 rounded-tl-sm'
        }`}>
          {isUser && (
            <p className="whitespace-pre-wrap">{message.text}</p>
          )}

          {!isUser && isEmpty && <TypingIndicator />}

          {!isUser && !isEmpty && isError && (
            <div className="flex items-center gap-2">
              <AlertCircle size={14} className="text-red-500 flex-shrink-0" />
              <span>{message.text}</span>
            </div>
          )}

          {!isUser && !isEmpty && !isError && (
            <div className="text-sm text-slate-800 leading-relaxed space-y-2">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({children}) => <h1 className="text-base font-bold text-ida-navy mt-3 mb-1">{children}</h1>,
                  h2: ({children}) => <h2 className="text-sm font-bold text-ida-navy mt-3 mb-1">{children}</h2>,
                  h3: ({children}) => <h3 className="text-sm font-semibold text-ida-navy mt-2 mb-1">{children}</h3>,
                  p:  ({children}) => <p className="my-1 leading-relaxed">{children}</p>,
                  ul: ({children}) => <ul className="list-disc pl-5 space-y-0.5 my-1">{children}</ul>,
                  ol: ({children}) => <ol className="list-decimal pl-5 space-y-0.5 my-1">{children}</ol>,
                  li: ({children}) => <li className="leading-relaxed">{children}</li>,
                  strong: ({children}) => <strong className="font-semibold text-ida-navy">{children}</strong>,
                  // Inline code vs fenced code block
                  code: ({inline, children}) => inline
                    ? <code className="bg-blue-50 text-ida-blue px-1.5 py-0.5 rounded text-xs font-mono border border-blue-100">{children}</code>
                    : <code className="block rounded-xl p-4 overflow-x-auto text-xs font-mono leading-relaxed my-2 whitespace-pre border-l-4"
                        style={{background:'#EFF6FF', color:'#0D2545', borderLeftColor:'#E05D0D'}}>{children}</code>,
                  pre: ({children}) => <>{children}</>,
                  // Table with IDA navy header + striped rows
                  table: ({children}) => (
                    <div className="overflow-x-auto my-3 rounded-xl border border-slate-200 shadow-sm">
                      <table className="w-full text-xs border-collapse">{children}</table>
                    </div>
                  ),
                  thead: ({children}) => <thead style={{background:'linear-gradient(135deg,#0D2545,#1A3D6B)'}}>{children}</thead>,
                  th: ({children}) => <th className="px-4 py-2.5 text-left font-semibold text-white tracking-wide">{children}</th>,
                  tbody: ({children}) => <tbody>{children}</tbody>,
                  tr: ({children}) => <tr className="border-t border-slate-100 even:bg-slate-50 hover:bg-blue-50 transition-colors">{children}</tr>,
                  td: ({children}) => <td className="px-4 py-2 text-slate-700">{children}</td>,
                }}
              >
                {message.text}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Citations */}
        {message.citations?.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <p className="w-full text-[10px] text-slate-400 font-medium uppercase tracking-wider mb-0.5">
              Sources
            </p>
            {message.citations.map((c, i) => (
              <CitationChip key={i} citation={c} index={i} />
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}
