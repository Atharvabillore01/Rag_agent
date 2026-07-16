import { useEffect, useRef, useState } from 'react'
import { motion, useMotionValue } from 'framer-motion'

/**
 * DuckField — a cozy grass-field scene with a small white duck that roams it.
 *
 * The duck walks (proper waddle: alternating legs, side-to-side body sway,
 * head bob) toward the mouse. When the pointer rests it idles; on the register
 * page (`guide`) it waddles over toward the sign-up form. When the password
 * field is focused the parent passes `expression="cover"` and the duck stops and
 * hides its eyes behind a wing (`"peek"` = password revealed, eyes showing).
 *
 * Fills its container (use as an absolute background layer). Pure inline SVG +
 * framer-motion, no external assets.
 */
export default function DuckField({ expression = null, guide = false, className = '' }) {
  // QA-only override: /register?duck=cover|peek forces a pose for screenshots.
  if (typeof window !== 'undefined') {
    const q = new URLSearchParams(window.location.search).get('duck')
    if (q) expression = q
  }
  const fieldRef = useRef(null)
  const posRef = useRef(guide ? 0.5 : 0.4) // 0..1 across the field
  const facingRef = useRef(1)
  const walkingRef = useRef(false)
  const mouseRef = useRef(null)
  const lastRef = useRef(0)

  const [facing, setFacing] = useState(1)
  const [walking, setWalking] = useState(false)
  const x = useMotionValue(0)

  useEffect(() => {
    function onMove(e) {
      const el = fieldRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const frac = (e.clientX - r.left) / r.width
      mouseRef.current = { frac, t: performance.now() }
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  useEffect(() => {
    let raf
    const covering = expression === 'cover' || expression === 'peek'
    const step = () => {
      const el = fieldRef.current
      const width = el ? el.clientWidth : 600
      const now = performance.now()
      const dt = lastRef.current ? Math.min(0.05, (now - lastRef.current) / 1000) : 0.016
      lastRef.current = now

      let target
      if (covering) target = posRef.current                       // freeze while hiding eyes
      else if (mouseRef.current && now - mouseRef.current.t < 2200) target = mouseRef.current.frac
      else if (guide) target = 0.86                               // waddle toward the sign-up form
      else target = 0.42
      target = Math.min(0.9, Math.max(0.1, target))

      const diff = target - posRef.current
      let walkingNow = false
      if (Math.abs(diff) > 0.012) {
        const stepAmt = Math.sign(diff) * Math.min(Math.abs(diff), 0.5 * dt)
        posRef.current += stepAmt
        walkingNow = true
        const f = stepAmt < 0 ? -1 : 1
        if (f !== facingRef.current) { facingRef.current = f; setFacing(f) }
      }
      if (walkingNow !== walkingRef.current) { walkingRef.current = walkingNow; setWalking(walkingNow) }
      x.set(posRef.current * width)
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [expression, guide, x])

  const mode = walking ? 'walk' : 'stand'
  const legDur = 0.46
  const legL = {
    stand: { rotate: 0 },
    walk: { rotate: [-20, 20, -20], transition: { repeat: Infinity, duration: legDur, ease: 'easeInOut' } },
  }
  const legR = {
    stand: { rotate: 0 },
    walk: { rotate: [20, -20, 20], transition: { repeat: Infinity, duration: legDur, ease: 'easeInOut' } },
  }
  const bodyV = {
    stand: { rotate: 0, y: [0, -2, 0], transition: { repeat: Infinity, duration: 3, ease: 'easeInOut' } },
    walk: { rotate: [-3, 3, -3], y: [0, -4, 0], transition: { repeat: Infinity, duration: legDur, ease: 'easeInOut' } },
  }
  const headV = {
    stand: { x: 0 },
    walk: { x: [0, 4, 0], transition: { repeat: Infinity, duration: legDur, ease: 'easeInOut' } },
  }
  const wing = {
    stand: { rotate: 0, x: 0, y: 0 },
    walk: { rotate: [0, -8, 0], x: 0, y: 0, transition: { repeat: Infinity, duration: legDur, ease: 'easeInOut' } },
    cover: { rotate: -96, x: 56, y: -46 },
    peek: { rotate: -82, x: 56, y: -34 },
  }
  const wingMode = expression === 'cover' ? 'cover' : expression === 'peek' ? 'peek' : mode

  return (
    <div ref={fieldRef} className={`absolute inset-0 overflow-hidden ${className}`}>
      {/* ── Sky ── */}
      <div className="absolute inset-0"
        style={{ background: 'linear-gradient(180deg,#173f31 0%,#256a4c 40%,#3d8f5f 68%,#4fa76d 100%)' }} />
      {/* warm sun glow */}
      <div className="absolute -top-16 -right-10 w-[380px] h-[380px] rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(255,224,150,0.35) 0%, transparent 70%)' }} />
      {/* soft clouds */}
      <div className="absolute top-[14%] left-[12%] w-40 h-14 rounded-full bg-white/10 blur-xl" />
      <div className="absolute top-[22%] right-[22%] w-52 h-16 rounded-full bg-white/[0.08] blur-xl" />

      {/* ── Rolling hills + grass (bottom scene) ── */}
      <svg className="absolute bottom-0 left-0 w-full" viewBox="0 0 100 46" preserveAspectRatio="none"
        style={{ height: '52%' }}>
        <path d="M0 16 Q25 4 50 12 T100 10 L100 46 L0 46 Z" fill="#2f8050" opacity="0.85" />
        <path d="M0 24 Q30 12 60 20 T100 18 L100 46 L0 46 Z" fill="#2a7247" />
        <path d="M0 30 Q35 22 70 28 T100 26 L100 46 L0 46 Z" fill="#236238" />
      </svg>

      {/* grass tufts + flowers along the front */}
      <svg className="absolute bottom-0 left-0 w-full" viewBox="0 0 400 60" preserveAspectRatio="none" style={{ height: '18%' }}>
        <g stroke="#1f5731" strokeWidth="3" strokeLinecap="round" fill="none" opacity="0.9">
          <path d="M20 58 q-3 -18 3 -28" /><path d="M30 58 q2 -14 9 -22" /><path d="M40 58 q4 -18 -2 -30" />
          <path d="M150 58 q-3 -16 3 -26" /><path d="M160 58 q3 -14 10 -20" />
          <path d="M300 58 q-3 -18 4 -28" /><path d="M312 58 q3 -14 10 -22" /><path d="M322 58 q4 -16 -2 -28" />
        </g>
      </svg>
      <div className="absolute left-[18%] bottom-[7%] w-2 h-2 rounded-full bg-[#FF6FA0]" />
      <div className="absolute left-[62%] bottom-[9%] w-2 h-2 rounded-full bg-[#FFD27A]" />
      <div className="absolute left-[80%] bottom-[6%] w-2 h-2 rounded-full bg-[#FF6FA0]" />

      {/* ── The duck (roams horizontally in the grass band) ── */}
      <motion.div className="absolute" style={{ x, bottom: '4%', left: 0, width: 132, marginLeft: -66 }}>
        <div style={{ transform: `scaleX(${facing})` }}>
          <svg viewBox="0 0 180 170" className="w-full h-auto overflow-visible"
            style={{ filter: 'drop-shadow(0 10px 10px rgba(6,24,14,0.35))' }}>
            <defs>
              <radialGradient id="dfBody" cx="42%" cy="30%" r="82%">
                <stop offset="0%" stopColor="#FFFFFF" /><stop offset="62%" stopColor="#F2F5FA" /><stop offset="100%" stopColor="#D6DEEC" />
              </radialGradient>
              <radialGradient id="dfHead" cx="44%" cy="34%" r="78%">
                <stop offset="0%" stopColor="#FFFFFF" /><stop offset="70%" stopColor="#F4F7FC" /><stop offset="100%" stopColor="#DCE3EF" />
              </radialGradient>
              <linearGradient id="dfBill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#FFB03A" /><stop offset="100%" stopColor="#F07E0C" />
              </linearGradient>
              <linearGradient id="dfFoot" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#FCA22E" /><stop offset="100%" stopColor="#E5760A" />
              </linearGradient>
              <linearGradient id="dfWing" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#FFFFFF" /><stop offset="100%" stopColor="#CDD6E6" />
              </linearGradient>
            </defs>

            {/* legs (behind body) */}
            <motion.g variants={legL} animate={mode} style={{ transformBox: 'fill-box', transformOrigin: '84px 104px' }}>
              <rect x="80" y="104" width="7" height="26" rx="3.5" fill="#E5760A" />
              <path d="M72 130 q11 -6 22 0 q-2 8 -11 8 q-9 0 -11 -8 z" fill="url(#dfFoot)" />
            </motion.g>
            <motion.g variants={legR} animate={mode} style={{ transformBox: 'fill-box', transformOrigin: '104px 104px' }}>
              <rect x="100" y="104" width="7" height="26" rx="3.5" fill="#F0810C" />
              <path d="M92 130 q11 -6 22 0 q-2 8 -11 8 q-9 0 -11 -8 z" fill="url(#dfFoot)" />
            </motion.g>

            {/* body + head (sway together) */}
            <motion.g variants={bodyV} animate={mode} style={{ transformBox: 'fill-box', transformOrigin: '90px 108px' }}>
              {/* tail */}
              <path d="M28 78 q-18 -6 -22 8 q14 10 30 2 z" fill="#EDF1F8" />
              {/* body */}
              <ellipse cx="86" cy="86" rx="58" ry="44" fill="url(#dfBody)" transform="rotate(-6 86 86)" />
              <ellipse cx="78" cy="100" rx="40" ry="26" fill="#C9D3E4" opacity="0.35" />

              {/* neck + head */}
              <motion.g variants={headV} animate={mode} style={{ transformBox: 'fill-box', transformOrigin: '120px 90px' }}>
                <path d="M112 74 q6 -26 26 -30 q10 24 -6 40 q-16 8 -20 -10 z" fill="url(#dfHead)" />
                <circle cx="138" cy="46" r="24" fill="url(#dfHead)" />
                {/* tuft */}
                <g stroke="#DCE3EF" strokeWidth="4" strokeLinecap="round" fill="none">
                  <path d="M138 24 q-3 -7 -10 -8" /><path d="M140 23 q3 -7 10 -7" />
                </g>
                {/* eye */}
                <circle cx="148" cy="42" r="4.4" fill="#152444" />
                <circle cx="146.4" cy="40.4" r="1.5" fill="#fff" />
                {/* cheek */}
                <ellipse cx="132" cy="54" rx="7" ry="4.5" fill="#FF9A6B" opacity="0.3" />
                {/* bill */}
                <path d="M150 40 q22 -3 30 6 q-8 8 -30 6 z" fill="url(#dfBill)" />
                <path d="M152 52 q18 4 26 0 q-6 8 -16 8 q-9 0 -10 -8 z" fill="#D96C08" opacity="0.9" />
                <circle cx="170" cy="45" r="1.8" fill="#B4560A" />
              </motion.g>

              {/* wing (rests on body; lifts to cover the eye) */}
              <motion.g variants={wing} animate={wingMode}
                transition={wingMode === 'cover' || wingMode === 'peek' ? { type: 'spring', stiffness: 260, damping: 20 } : undefined}
                style={{ transformBox: 'fill-box', transformOrigin: '96px 74px' }}>
                <path d="M64 78 q34 -16 68 -4 q-4 30 -34 34 q-30 2 -34 -30 z" fill="url(#dfWing)" />
                <g stroke="#C2CCDE" strokeWidth="2.5" fill="none" strokeLinecap="round" opacity="0.9">
                  <path d="M78 84 q22 -6 42 0" /><path d="M80 94 q20 -5 38 0" />
                </g>
              </motion.g>
            </motion.g>
          </svg>
        </div>
      </motion.div>
    </div>
  )
}
