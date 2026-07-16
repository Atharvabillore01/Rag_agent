import { useId } from 'react'
import { motion } from 'framer-motion'

// Animated brand mark — a vault combination dial. Pure inline SVG + framer-motion
// (no external image, no WebGL), so it stays crisp at any size, renders identically
// offline / air-gapped, and is cheap to mount in several places at once.
//
// Motion: the outer tick ring rotates one way, the inner dial dome counter-rotates,
// and the amber core breathes — reads as a live, self-locking vault.

const TICKS = Array.from({ length: 12 }, (_, i) => i * 30)

function VaultMark({ size = 44, spin = true }) {
  const uid = useId().replace(/:/g, '')
  const bg = `bg-${uid}`
  const dome = `dome-${uid}`
  const core = `core-${uid}`
  const sheen = `sheen-${uid}`

  // transform-box:view-box + a fixed origin => rotate/scale about the true center
  // (32,32) with no wobble, regardless of each group's own bounding box.
  const spinBase = { transformBox: 'view-box', transformOrigin: '32px 32px', willChange: 'transform' }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className="flex-shrink-0"
      style={{ filter: 'drop-shadow(0 4px 10px rgba(13,37,69,0.35))' }}
    >
      <defs>
        <linearGradient id={bg} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#16305e" />
          <stop offset="55%" stopColor="#0D2545" />
          <stop offset="100%" stopColor="#0A1B34" />
        </linearGradient>
        <radialGradient id={dome} cx="38%" cy="34%" r="72%">
          <stop offset="0%" stopColor="#3B76F0" />
          <stop offset="55%" stopColor="#1A56DB" />
          <stop offset="100%" stopColor="#123A9E" />
        </radialGradient>
        <radialGradient id={core} cx="42%" cy="38%" r="70%">
          <stop offset="0%" stopColor="#FFD27A" />
          <stop offset="55%" stopColor="#F5A623" />
          <stop offset="100%" stopColor="#E05D0D" />
        </radialGradient>
        <linearGradient id={sheen} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Vault body */}
      <rect x="1.5" y="1.5" width="61" height="61" rx="16" fill={`url(#${bg})`} />
      <rect x="1.5" y="1.5" width="61" height="61" rx="16" fill="none"
            stroke="#ffffff" strokeOpacity="0.14" strokeWidth="1" />
      {/* Top gloss */}
      <rect x="6" y="5" width="52" height="22" rx="12" fill={`url(#${sheen})`} opacity="0.5" />

      {/* Outer tick ring — slow clockwise spin */}
      <motion.g
        style={spinBase}
        animate={spin ? { rotate: 360 } : { rotate: 0 }}
        transition={{ repeat: Infinity, ease: 'linear', duration: 18 }}
      >
        <circle cx="32" cy="32" r="22" fill="none" stroke="#1A56DB" strokeOpacity="0.35" strokeWidth="1.5" />
        {TICKS.map((deg, i) => (
          <rect
            key={deg}
            x="31" y="7" width="2" height={i % 3 === 0 ? 5 : 3} rx="1"
            fill="#9DBBFF" fillOpacity={i % 3 === 0 ? 0.95 : 0.55}
            transform={`rotate(${deg} 32 32)`}
          />
        ))}
      </motion.g>

      {/* Inner dial dome — faster counter-clockwise spin */}
      <motion.g
        style={spinBase}
        animate={spin ? { rotate: -360 } : { rotate: 0 }}
        transition={{ repeat: Infinity, ease: 'linear', duration: 11 }}
      >
        <circle cx="32" cy="32" r="14" fill={`url(#${dome})`} />
        <circle cx="32" cy="32" r="14" fill="none" stroke="#0A1B34" strokeOpacity="0.4" strokeWidth="1" />
        {/* dial pointer / spoke */}
        <rect x="30.8" y="20" width="2.4" height="7" rx="1.2" fill="#EAF1FF" />
        <circle cx="32" cy="32" r="14" fill="none" stroke="#ffffff" strokeOpacity="0.18" strokeWidth="1"
                strokeDasharray="2 6" />
      </motion.g>

      {/* Breathing amber core (the "unlocked" heart of the vault) */}
      <motion.circle
        cx="32" cy="32" r="5.2" fill={`url(#${core})`}
        style={{ transformBox: 'view-box', transformOrigin: '32px 32px' }}
        animate={{ scale: [1, 1.16, 1], opacity: [0.9, 1, 0.9] }}
        transition={{ repeat: Infinity, ease: 'easeInOut', duration: 2.4 }}
      />
      <circle cx="30.4" cy="30.2" r="1.5" fill="#ffffff" fillOpacity="0.7" />
    </svg>
  )
}

export default function DuckVaultLogo({ size = 'md', white = false, animated = true }) {
  const cfg = {
    sm: { mark: 36, titlePx: 18, subPx: 10, gap: 10 },
    md: { mark: 46, titlePx: 22, subPx: 11, gap: 13 },
    lg: { mark: 56, titlePx: 27, subPx: 13, gap: 15 },
    xl: { mark: 68, titlePx: 34, subPx: 15, gap: 17 },
  }
  const { mark, titlePx, subPx, gap } = cfg[size] || cfg.md

  return (
    <div className="flex items-center" style={{ gap }}>
      <VaultMark size={mark} spin={animated} />
      <div>
        <p
          style={{ fontSize: titlePx, letterSpacing: '-0.3px' }}
          className={`font-display font-extrabold leading-none ${white ? 'text-white' : 'text-duck-navy'}`}
        >
          DuckVault
        </p>
        <p
          style={{ fontSize: subPx }}
          className={`font-medium leading-tight mt-0.5 ${white ? 'text-white/60' : 'text-slate-500'}`}
        >
          AI Document Intelligence
        </p>
        <div
          style={{
            width: titlePx * 3.4, height: 2, marginTop: 3, borderRadius: 1,
            background: white ? 'rgba(245,166,35,0.85)' : '#E05D0D',
          }}
        />
      </div>
    </div>
  )
}
