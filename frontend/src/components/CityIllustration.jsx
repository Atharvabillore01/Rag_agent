import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const PROJECTS = [
  {
    name: 'Lata Mangeshkar Auditorium',
    type: 'Cultural & Community',
    img:  'https://www.idaindore.org/Content/img/slider/Lata-Mangeshkar.jpg',
  },
  {
    name: 'ISBT MR-10 Bus Terminal',
    type: 'Transport Infrastructure',
    img:  'https://www.idaindore.org/Content/img/slider/ISBT-MR10_3.jpg',
  },
  {
    name: 'Khajrana Flyover',
    type: 'Road Infrastructure',
    img:  'https://www.idaindore.org/Content/img/slider/KHAJRANA-FLYOVER.jpg',
  },
  {
    name: 'Bhawarkua Development',
    type: 'Urban Development',
    img:  'https://www.idaindore.org/Content/img/slider/bhawarkua.jpg',
  },
  {
    name: 'Nayata Mindla Project',
    type: 'Residential Scheme',
    img:  'https://www.idaindore.org/Content/img/slider/NAYATA-MINDLA_2.jpg',
  },
]

export default function CityIllustration({ className = '' }) {
  const [current, setCurrent] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setCurrent(c => (c + 1) % PROJECTS.length), 4000)
    return () => clearInterval(t)
  }, [])

  const proj = PROJECTS[current]

  return (
    <div className={`relative rounded-2xl overflow-hidden shadow-elevated ${className}`}
         style={{ aspectRatio: '16/9' }}>
      {/* Rotating property photo */}
      <AnimatePresence mode="wait">
        <motion.img
          key={current}
          src={proj.img}
          alt={proj.name}
          initial={{ opacity: 0, scale: 1.06 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.97 }}
          transition={{ duration: 0.9, ease: 'easeInOut' }}
          className="absolute inset-0 w-full h-full object-cover"
        />
      </AnimatePresence>

      {/* Gradient overlay — bottom strong, top subtle */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />

      {/* IDA badge top-left */}
      <div className="absolute top-3 left-3 flex items-center gap-2 px-2.5 py-1.5 rounded-lg
                      bg-white/15 backdrop-blur-sm border border-white/20">
        <img
          src="https://www.idaindore.org/assets/img/logo.png"
          alt="IDA"
          className="h-5 w-auto object-contain"
        />
        <span className="text-white text-[11px] font-bold tracking-wide">IDA Project</span>
      </div>

      {/* Project name overlay */}
      <AnimatePresence mode="wait">
        <motion.div
          key={current}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.45 }}
          className="absolute bottom-0 left-0 right-0 p-4"
        >
          <p className="text-white/60 text-[10px] font-semibold uppercase tracking-widest mb-0.5">
            {proj.type}
          </p>
          <p className="text-white font-display font-bold text-base leading-tight">
            {proj.name}
          </p>
        </motion.div>
      </AnimatePresence>

      {/* Dot indicators */}
      <div className="absolute bottom-4 right-4 flex gap-1.5">
        {PROJECTS.map((_, i) => (
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
