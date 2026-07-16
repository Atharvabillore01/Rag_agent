import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, MessageSquare, Sparkles, FileSearch, FileText, ListChecks } from 'lucide-react'
import { streamQuery } from '../api'
import { useChatStore } from '../stores/chatStore'
import { useAuthStore } from '../stores/authStore'
import MessageBubble from '../components/MessageBubble'
import AgentStatus from '../components/AgentStatus'

const SUGGESTIONS = [
  { icon: FileSearch, text: 'Summarize this document and list its key points.',              label: 'Summarize'  },
  { icon: ListChecks, text: 'What are the important dates, deadlines, and amounts in these files?', label: 'Key Facts' },
  { icon: FileText,   text: 'Find the clauses about termination, liability, and payment terms.',    label: 'Find Clauses' },
  { icon: Sparkles,   text: 'Compare these documents and highlight the differences.',          label: 'Compare'    },
]

function WelcomeScreen({ onSuggest }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center h-full px-6 py-12 text-center"
    >
      <div className="w-16 h-16 rounded-2xl bg-duck-grad flex items-center justify-center mb-5 shadow-elevated">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r="10"  stroke="white" strokeWidth="2.4" opacity="0.9"/>
          <circle cx="16" cy="16" r="4.2" stroke="white" strokeWidth="2.2"/>
          <circle cx="16" cy="16" r="1.5" fill="#F5A623"/>
          <rect x="15" y="2"  width="2" height="4" rx="1" fill="white" opacity="0.8"/>
          <rect x="15" y="26" width="2" height="4" rx="1" fill="white" opacity="0.8"/>
        </svg>
      </div>
      <h1 className="text-2xl font-display font-bold text-duck-navy mb-1">Welcome to DuckVault</h1>
      <p className="text-slate-500 text-sm mb-8">Ask your documents anything — grounded answers with citations.</p>
      <div className="w-full max-w-lg grid grid-cols-2 gap-3">
        {SUGGESTIONS.map(({ icon: Icon, text, label }) => (
          <motion.button
            key={label}
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => onSuggest(text)}
            className="card-hover text-left p-4 flex flex-col gap-2.5 group"
          >
            <div className="w-8 h-8 rounded-lg bg-duck-blue-pale flex items-center justify-center group-hover:bg-duck-blue group-hover:text-white transition-colors">
              <Icon size={15} className="text-duck-blue group-hover:text-white transition-colors" />
            </div>
            <div>
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">{label}</p>
              <p className="text-xs text-slate-600 leading-tight">{text}</p>
            </div>
          </motion.button>
        ))}
      </div>
    </motion.div>
  )
}

export default function Chat() {
  const [input, setInput] = useState('')
  const bottomRef         = useRef(null)
  const inputRef          = useRef(null)

  const {
    currentMessages, streaming, statusSteps, thoughts,
    addUserMessage, startAssistantMessage, appendToken,
    addCitation, finalizeMessage, setError: setChatError,
    pushStatus, pushThought,
  } = useChatStore()

  const messages = currentMessages()
  const user = useAuthStore(s => s.user)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, statusSteps])

  async function send(question) {
    if (!question.trim() || streaming) return
    setInput('')

    addUserMessage(question)
    const msgId = Date.now() + 1
    startAssistantMessage(msgId)

    try {
      for await (const event of streamQuery(question)) {
        switch (event.event_type) {
          case 'status':
            pushStatus(event.message)
            break
          case 'thinking':
            pushThought(event.message)
            break
          case 'token_delta':
            appendToken(msgId, event.token)
            break
          case 'citation':
            addCitation(msgId, event)
            break
          case 'final_answer':
            finalizeMessage(msgId, event.answer, event.citations || [], event.followups || [])
            break
          case 'error':
            setChatError(msgId, event.message)
            break
        }
      }
    } catch (err) {
      setChatError(msgId, err.message || 'Something went wrong. Please try again.')
    }

    setTimeout(() => inputRef.current?.focus(), 100)
  }

  function handleSubmit(e) { e.preventDefault(); send(input) }
  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) }
  }

  const hasMessages = messages.length > 0

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* Header */}
      <div className="flex items-center px-6 py-4 bg-white border-b border-slate-100 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-duck-blue-pale flex items-center justify-center">
            <MessageSquare size={18} className="text-duck-blue" />
          </div>
          <div>
            <h2 className="font-display font-semibold text-duck-navy text-sm">AI Assistant</h2>
            <p className="text-[11px] text-slate-400">
              {streaming
                ? <span className="text-duck-blue font-medium flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-duck-blue animate-pulse inline-block" />
                    Processing your query…
                  </span>
                : 'Ask about any document in your workspace'}
            </p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {!hasMessages ? (
          <WelcomeScreen onSuggest={t => { setInput(t); setTimeout(() => send(t), 50) }} />
        ) : (
          <div className="py-6 space-y-6">
            <AnimatePresence>
              {messages.map(msg => <MessageBubble key={msg.id} message={msg} />)}
            </AnimatePresence>

            <AnimatePresence>
              {(streaming || statusSteps.length > 0) && (
                <AgentStatus steps={statusSteps} thoughts={thoughts} streaming={streaming} />
              )}
            </AnimatePresence>

            {/* Suggested follow-ups for the latest answer */}
            {!streaming && (() => {
              const last = messages[messages.length - 1]
              const fus = last && last.role === 'assistant' && last.status === 'done' ? (last.followups || []) : []
              return fus.length > 0 ? (
                <div className="max-w-3xl mx-auto px-4 flex flex-wrap gap-2">
                  <span className="w-full text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Follow-up questions</span>
                  {fus.map((q, i) => (
                    <button key={i} onClick={() => send(q)}
                      className="text-xs text-duck-blue bg-duck-blue-pale border border-blue-100 rounded-full px-3 py-1.5 hover:bg-blue-50 text-left transition-colors">
                      {q}
                    </button>
                  ))}
                </div>
              ) : null
            })()}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex-shrink-0 border-t border-slate-100 bg-white px-4 py-4">
        <form onSubmit={handleSubmit} className="flex items-end gap-3">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your documents, or describe what you need drafted…"
              rows={1}
              disabled={streaming}
              className="w-full resize-none input-field pr-4 py-3.5 text-sm leading-relaxed
                         min-h-[52px] max-h-[160px] overflow-y-auto scrollbar-thin
                         disabled:opacity-60 disabled:cursor-not-allowed"
              style={{ height: 'auto' }}
              onInput={e => {
                e.target.style.height = 'auto'
                e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
              }}
            />
          </div>
          <motion.button
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
            type="submit"
            disabled={!input.trim() || streaming}
            className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0
                       disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
            style={{ background: 'linear-gradient(135deg, #1A56DB 0%, #1648C0 100%)' }}
          >
            {streaming
              ? <div className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              : <Send size={17} className="text-white translate-x-0.5" />}
          </motion.button>
        </form>
        <p className="text-[10px] text-slate-400 mt-2 text-center">
          Press Enter to send · Shift+Enter for new line · Responses are AI-generated, verify for official use
        </p>
      </div>
    </div>
  )
}
