import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Brain, Search, ShieldCheck, Sparkles, Target, CheckCircle2, Loader2, ChevronDown, Lightbulb, Activity } from 'lucide-react'

const STEP_ICONS = {
  'Classifying':   Brain,
  'Planning':      Target,
  'Searching':     Search,
  'Verifying':     ShieldCheck,
  'Generating':    Sparkles,
  'Reformulating': Brain,
}

function getStepIcon(message) {
  for (const [key, Icon] of Object.entries(STEP_ICONS)) {
    if (message.toLowerCase().includes(key.toLowerCase())) return Icon
  }
  return Loader2
}

function formatMs(ms) {
  if (ms == null) return ''
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

export default function AgentStatus({ steps = [], thoughts = [], streaming }) {
  const [thoughtsOpen, setThoughtsOpen] = useState(false)
  const [pipelineOpen, setPipelineOpen] = useState(true)

  // Auto-collapse pipeline once all steps are done and streaming has stopped
  useEffect(() => {
    if (!streaming && steps.length > 0 && steps.every(s => s.done)) {
      const t = setTimeout(() => setPipelineOpen(false), 800)
      return () => clearTimeout(t)
    }
  }, [streaming, steps])

  // Re-open when a new query starts
  useEffect(() => {
    if (streaming) setPipelineOpen(true)
  }, [streaming])

  if (!steps.length && !streaming) return null

  const doneCount = steps.filter(s => s.done).length
  const totalMs   = steps.reduce((sum, s) => sum + (s.elapsed_ms || 0), 0)

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      className="mx-4 mb-3"
    >
      <div className="card px-4 py-3 border border-slate-100">
        {/* Header — always visible, click to toggle */}
        <button
          onClick={() => setPipelineOpen(o => !o)}
          className="flex items-center gap-2 w-full text-left group"
        >
          <Activity size={12} className="text-ida-blue flex-shrink-0" />
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest flex-1">
            AI Agent Pipeline
          </span>
          {!pipelineOpen && doneCount > 0 && (
            <span className="text-[10px] text-slate-400 font-mono bg-slate-50 px-1.5 py-0.5 rounded mr-1">
              {doneCount} steps · {formatMs(totalMs)}
            </span>
          )}
          <ChevronDown
            size={13}
            className={`text-slate-400 group-hover:text-ida-blue transition-all ${pipelineOpen ? 'rotate-180' : ''}`}
          />
        </button>

        <AnimatePresence initial={false}>
          {pipelineOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="mt-2.5 space-y-2">
        <AnimatePresence>
            {steps.map((step, i) => {
              const Icon = getStepIcon(step.message)
              const isLast = i === steps.length - 1
              const isActive = isLast && !step.done && streaming

              return (
                <motion.div
                  key={step.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.05 }}
                  className="flex items-center gap-3"
                >
                  <div className="flex flex-col items-center flex-shrink-0">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center ${
                      step.done
                        ? 'bg-emerald-50'
                        : isActive
                          ? 'bg-ida-blue-pale animate-pulse-r'
                          : 'bg-slate-50'
                    }`}>
                      {step.done
                        ? <CheckCircle2 size={14} className="text-emerald-500" />
                        : isActive
                          ? <Icon size={14} className="text-ida-blue animate-spin-slow" />
                          : <Icon size={14} className="text-slate-300" />}
                    </div>
                    {i < steps.length - 1 && (
                      <div className={`w-px h-2 mt-0.5 ${step.done ? 'bg-emerald-200' : 'bg-slate-100'}`} />
                    )}
                  </div>

                  <p className={`text-xs leading-tight flex-1 ${
                    step.done ? 'text-slate-500' : isActive ? 'text-ida-blue font-medium' : 'text-slate-400'
                  }`}>
                    {step.message}
                  </p>

                  {step.done && step.elapsed_ms != null && (
                    <span className="text-[10px] text-slate-400 font-mono bg-slate-50 px-1.5 py-0.5 rounded flex-shrink-0">
                      {formatMs(step.elapsed_ms)}
                    </span>
                  )}

                  {isActive && (
                    <div className="flex gap-1 ml-auto">
                      <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
                    </div>
                  )}
                </motion.div>
              )
            })}
          </AnimatePresence>

                {/* Agent reasoning (collapsible, inside pipeline wrapper) */}
                {thoughts.length > 0 && (
                  <div className="mt-3 border-t border-slate-100 pt-2.5">
                    <button
                      onClick={() => setThoughtsOpen(o => !o)}
                      className="flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-ida-blue transition-colors w-full text-left"
                    >
                      <Lightbulb size={12} className="text-amber-400" />
                      <span className="font-medium">Agent reasoning</span>
                      <ChevronDown size={12} className={`ml-auto transition-transform ${thoughtsOpen ? 'rotate-180' : ''}`} />
                    </button>
                    <AnimatePresence>
                      {thoughtsOpen && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="overflow-hidden"
                        >
                          <div className="mt-2 space-y-1.5">
                            {thoughts.map(t => (
                              <div key={t.id} className="bg-amber-50 rounded-lg px-3 py-2">
                                <pre className="text-[11px] text-amber-800 whitespace-pre-wrap font-mono leading-relaxed">
                                  {t.message}
                                </pre>
                              </div>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
