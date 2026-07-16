import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, Search, Languages, GitCompareArrows } from 'lucide-react'

// Self-contained product illustration — no external image dependencies, so it
// renders identically offline and in air-gapped deployments.
const SCENES = [
  { icon: Search,           label: 'Ask & cite',   caption: 'Answers grounded in your files' },
  { icon: Languages,        label: 'OCR & translate', caption: 'Scanned & multi-language docs' },
  { icon: GitCompareArrows, label: 'Compare',      caption: 'Redline & parallel review' },
  { icon: FileText,         label: 'Draft',        caption: 'Generate documents in context' },
]

export default function CityIllustration({ className = '' }) {
  const [current, setCurrent] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setCurrent(c => (c + 1) % SCENES.length), 4000)
    return () => clearInterval(t)
  }, [])

  const scene = SCENES[current]
  const SceneIcon = scene.icon

  return (
    <div
      className={`relative rounded-2xl overflow-hidden shadow-elevated bg-duck-navy ${className}`}
      style={{ aspectRatio: '16/9' }}
    >
      {/* Ambient glows */}
      <div className="absolute -top-16 -right-10 w-56 h-56 rounded-full"
           style={{ background: 'radial-gradient(circle, rgba(26,86,219,0.45) 0%, transparent 70%)' }} />
      <div className="absolute -bottom-20 -left-8 w-56 h-56 rounded-full"
           style={{ background: 'radial-gradient(circle, rgba(245,166,35,0.20) 0%, transparent 70%)' }} />
      <div className="absolute inset-0 opacity-[0.10]"
           style={{ backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)', backgroundSize: '22px 22px' }} />

      {/* Centered rotating scene */}
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={current}
            initial={{ opacity: 0, scale: 0.85, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: -8 }}
            transition={{ duration: 0.5, ease: 'easeInOut' }}
            className="flex flex-col items-center"
          >
            <div className="w-16 h-16 rounded-2xl bg-white/10 border border-white/15 backdrop-blur-sm flex items-center justify-center mb-3">
              <SceneIcon size={28} className="text-white" />
            </div>
            <p className="text-white font-display font-bold text-lg leading-tight">{scene.label}</p>
            <p className="text-white/50 text-xs mt-0.5">{scene.caption}</p>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Dot indicators */}
      <div className="absolute bottom-4 right-4 flex gap-1.5">
        {SCENES.map((_, i) => (
          <button
            key={i}
            onClick={() => setCurrent(i)}
            className={`rounded-full transition-all duration-300 ${
              i === current ? 'w-4 h-1.5 bg-white' : 'w-1.5 h-1.5 bg-white/40 hover:bg-white/70'
            }`}
          />
        ))}
      </div>
    </div>
  )
}
