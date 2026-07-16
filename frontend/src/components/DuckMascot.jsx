import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion'

/**
 * DuckMascot — the DuckVault brand character, in a little garden.
 *
 * Behaviours:
 *  • follow  — eyes + head track the mouse; the duck leans/scoots toward it.
 *  • read    — idle: looks down and reads its book (auto after the mouse stops).
 *  • cover   — hides its eyes behind both wings (driven when the password field
 *              is focused, so it can't "peek" at your password).
 *  • peek    — wings still up but parted, eyes showing (password revealed).
 *  • cheer   — wings up, happy eyes (sign-up in progress — it's rooting for you).
 * When not reading, the book is stowed in its satchel.
 *
 * The parent controls the pose via `expression`; when that's null the duck runs
 * its own mouse-follow + idle logic. A `?duck=<mode>` query param can force a
 * pose (handy for visual QA). Pure inline SVG + framer-motion — no assets.
 */
export default function DuckMascot({ className = '', expression = null }) {
  const wrapRef = useRef(null)
  const [idle, setIdle] = useState(true)
  const [blink, setBlink] = useState(false)

  const forced = useMemo(() => {
    if (typeof window === 'undefined') return null
    return new URLSearchParams(window.location.search).get('duck')
  }, [])

  const mode = forced || expression || (idle ? 'read' : 'follow')

  // Gaze target (-1..1); springs give the follow some weight.
  const gx = useMotionValue(0)
  const gy = useMotionValue(0.5)
  const sx = useSpring(gx, { stiffness: 140, damping: 15, mass: 0.6 })
  const sy = useSpring(gy, { stiffness: 140, damping: 15, mass: 0.6 })

  const headRot = useTransform(sx, [-1, 1], [-8, 8])
  const headLift = useTransform(sy, [-1, 1], [-5, 7])
  const pupilX = useTransform(sx, [-1, 1], [-6.5, 6.5])
  const pupilY = useTransform(sy, [-1, 1], [-5, 6])
  const duckX = useTransform(sx, [-1, 1], [-22, 22]) // scoot toward cursor
  const duckRot = useTransform(sx, [-1, 1], [-4, 4])

  // Point the gaze based on the current (non-follow) pose.
  useEffect(() => {
    if (mode === 'read') { gx.set(0); gy.set(0.55) }
    else if (mode === 'cover' || mode === 'peek') { gx.set(0); gy.set(-0.05) }
    else if (mode === 'cheer') { gx.set(0); gy.set(-0.35) }
  }, [mode, gx, gy])

  // Mouse follow + idle detection (skipped when a pose is forced from outside).
  useEffect(() => {
    if (forced || expression) return
    let idleTimer
    function onMove(e) {
      const el = wrapRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const cx = r.left + r.width / 2
      const cy = r.top + r.height * 0.36
      gx.set(Math.max(-1, Math.min(1, (e.clientX - cx) / (r.width / 2))))
      gy.set(Math.max(-1, Math.min(1, (e.clientY - cy) / (r.height / 2))))
      setIdle(false)
      clearTimeout(idleTimer)
      idleTimer = setTimeout(() => setIdle(true), 2400)
    }
    window.addEventListener('mousemove', onMove)
    idleTimer = setTimeout(() => setIdle(true), 1200)
    return () => { window.removeEventListener('mousemove', onMove); clearTimeout(idleTimer) }
  }, [forced, expression, gx, gy])

  // Autonomous blinking.
  useEffect(() => {
    let t
    const loop = () => {
      t = setTimeout(() => {
        setBlink(true); setTimeout(() => setBlink(false), 150); loop()
      }, 1800 + Math.random() * 3200)
    }
    loop()
    return () => clearTimeout(t)
  }, [])

  // ── Pose variants ────────────────────────────────────────────────────────
  const wingL = {
    follow: { x: 0, y: 0, rotate: 8 },
    read:   { x: 12, y: 2, rotate: -14 },
    cover:  { x: 26, y: -96, rotate: 22 },
    peek:   { x: 26, y: -78, rotate: 22 },
    cheer:  { x: 4, y: -52, rotate: -34 },
  }
  const wingR = {
    follow: { x: 0, y: 0, rotate: -8 },
    read:   { x: -12, y: 2, rotate: 14 },
    cover:  { x: -26, y: -96, rotate: -22 },
    peek:   { x: -26, y: -78, rotate: -22 },
    cheer:  { x: -4, y: -52, rotate: 34 },
  }
  const bookV = {
    read:   { opacity: 1, y: 0, scale: 1 },
    follow: { opacity: 0, y: 46, scale: 0.6 },
    cover:  { opacity: 0, y: 46, scale: 0.6 },
    peek:   { opacity: 0, y: 46, scale: 0.6 },
    cheer:  { opacity: 0, y: 46, scale: 0.6 },
  }
  const openEyes = { cheer: { opacity: 0 }, follow: { opacity: 1 }, read: { opacity: 1 }, cover: { opacity: 1 }, peek: { opacity: 1 } }
  const happyEyes = { cheer: { opacity: 1 }, follow: { opacity: 0 }, read: { opacity: 0 }, cover: { opacity: 0 }, peek: { opacity: 0 } }
  const spring = { type: 'spring', stiffness: 260, damping: 20 }

  return (
    <div ref={wrapRef} className={`select-none ${className}`}>
      <motion.svg
        viewBox="0 0 300 340"
        className="w-full h-auto overflow-visible"
        animate={{ y: [0, -8, 0] }}
        transition={{ repeat: Infinity, duration: 4.5, ease: 'easeInOut' }}
        style={{ filter: 'drop-shadow(0 22px 34px rgba(6,18,38,0.45))' }}
      >
        <defs>
          <radialGradient id="dvBody" cx="40%" cy="30%" r="80%">
            <stop offset="0%" stopColor="#FFE787" /><stop offset="55%" stopColor="#FCC931" /><stop offset="100%" stopColor="#F2A81C" />
          </radialGradient>
          <radialGradient id="dvHead" cx="42%" cy="32%" r="78%">
            <stop offset="0%" stopColor="#FFEC96" /><stop offset="60%" stopColor="#FDD23F" /><stop offset="100%" stopColor="#F4B421" />
          </radialGradient>
          <linearGradient id="dvWing" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#FBC62A" /><stop offset="100%" stopColor="#EE9E10" />
          </linearGradient>
          <linearGradient id="dvBill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#FFB63F" /><stop offset="100%" stopColor="#F0810C" />
          </linearGradient>
          <linearGradient id="dvBook" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2E63E6" /><stop offset="100%" stopColor="#123A9E" />
          </linearGradient>
          <linearGradient id="dvGrass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3FBF6A" /><stop offset="100%" stopColor="#2E9E52" />
          </linearGradient>
        </defs>

        {/* ── Garden ground ── */}
        <ellipse cx="150" cy="322" rx="120" ry="20" fill="url(#dvGrass)" opacity="0.9" />
        <g stroke="#2E9E52" strokeWidth="5" strokeLinecap="round" fill="none" opacity="0.9">
          <path d="M54 318 q-4 -16 4 -26" /><path d="M64 320 q2 -14 12 -20" />
          <path d="M236 320 q-2 -16 -12 -22" /><path d="M248 318 q4 -14 -4 -26" />
        </g>
        {/* little tulip */}
        <g>
          <path d="M262 318 q0 -22 0 -30" stroke="#2E9E52" strokeWidth="4" fill="none" strokeLinecap="round" />
          <path d="M262 288 q-12 -2 -10 -14 q10 2 10 14 q0 -12 10 -14 q2 12 -10 14 z" fill="#FF6FA0" />
          <circle cx="262" cy="286" r="3.5" fill="#FFD27A" />
        </g>

        {/* ── Duck (scoots toward cursor) ── */}
        <motion.g style={{ x: duckX, rotate: duckRot, transformBox: 'fill-box', transformOrigin: '150px 316px' }}>
          {/* feet */}
          <g fill="#F0810C">
            <path d="M120 288 q-22 4 -30 20 q22 8 40 -1 q4 -12 -10 -19 z" />
            <path d="M180 288 q22 4 30 20 q-22 8 -40 -1 q-4 -12 10 -19 z" />
          </g>

          {/* tail flip */}
          <path d="M62 196 q-30 -6 -40 10 q26 14 46 2 z" fill="#F2A81C" />

          {/* body */}
          <ellipse cx="150" cy="206" rx="92" ry="84" fill="url(#dvBody)" />
          <ellipse cx="138" cy="228" rx="60" ry="46" fill="#FFFFFF" opacity="0.22" />

          {/* satchel (book lives here when not reading) */}
          <g>
            <path d="M196 214 l40 -14" stroke="#8A5A2B" strokeWidth="6" strokeLinecap="round" fill="none" opacity="0.9" />
            <rect x="196" y="212" width="52" height="46" rx="12" fill="#A9713A" />
            <rect x="196" y="212" width="52" height="18" rx="9" fill="#8A5A2B" />
            <circle cx="222" cy="236" r="4" fill="#5E3C18" />
          </g>

          {/* HEAD — tilts + lifts with gaze */}
          <motion.g style={{ rotate: headRot, y: headLift, transformBox: 'fill-box', transformOrigin: '150px 200px' }}>
            <g stroke="#F4B421" strokeWidth="7" strokeLinecap="round" fill="none">
              <path d="M150 52 q-8 -16 -22 -18" /><path d="M150 52 q0 -20 0 -24" /><path d="M150 52 q8 -16 22 -18" />
            </g>
            <circle cx="150" cy="112" r="72" fill="url(#dvHead)" />
            <ellipse cx="98" cy="134" rx="15" ry="10" fill="#FF9A6B" opacity="0.35" />
            <ellipse cx="202" cy="134" rx="15" ry="10" fill="#FF9A6B" opacity="0.35" />

            {/* open eyes */}
            <motion.g variants={openEyes} animate={mode} transition={{ duration: 0.2 }}>
              <ellipse cx="122" cy="104" rx="19" ry="22" fill="#FFFFFF" />
              <ellipse cx="178" cy="104" rx="19" ry="22" fill="#FFFFFF" />
              <motion.g style={{ x: pupilX, y: pupilY }}>
                <circle cx="122" cy="106" r="9.5" fill="#152444" /><circle cx="178" cy="106" r="9.5" fill="#152444" />
                <circle cx="119" cy="102" r="3" fill="#FFFFFF" /><circle cx="175" cy="102" r="3" fill="#FFFFFF" />
              </motion.g>
              {/* eyelids for blink */}
              <motion.g animate={{ scaleY: blink ? 1 : 0 }} transition={{ duration: 0.08 }} style={{ transformBox: 'fill-box', transformOrigin: 'top' }}>
                <rect x="102" y="80" width="40" height="26" rx="12" fill="url(#dvHead)" />
                <rect x="158" y="80" width="40" height="26" rx="12" fill="url(#dvHead)" />
              </motion.g>
            </motion.g>

            {/* happy (cheer) eyes */}
            <motion.g variants={happyEyes} animate={mode} transition={{ duration: 0.2 }} stroke="#152444" strokeWidth="5" strokeLinecap="round" fill="none">
              <path d="M108 108 q14 -16 28 0" /><path d="M164 108 q14 -16 28 0" />
            </motion.g>

            {/* bill */}
            <g>
              <path d="M118 136 q32 -14 64 0 q-6 30 -32 30 q-26 0 -32 -30 z" fill="url(#dvBill)" />
              <path d="M124 148 q26 12 52 0 q-8 18 -26 18 q-18 0 -26 -18 z" fill="#D96C08" opacity="0.85" />
              <circle cx="139" cy="140" r="2.6" fill="#B4560A" /><circle cx="161" cy="140" r="2.6" fill="#B4560A" />
            </g>
          </motion.g>

          {/* BOOK — visible only when reading */}
          <motion.g variants={bookV} animate={mode} transition={{ duration: 0.4, ease: 'easeOut' }}
            style={{ transformBox: 'fill-box', transformOrigin: '150px 250px' }}>
            <path d="M150 228 q-42 -14 -78 -2 l0 62 q38 -12 78 0 z" fill="#F3F7FF" />
            <path d="M150 228 q42 -14 78 -2 l0 62 q-38 -12 -78 0 z" fill="#E7EEFC" />
            <path d="M68 224 q40 -14 82 -2 l0 8 q-42 -12 -80 0 z" fill="url(#dvBook)" />
            <path d="M232 224 q-40 -14 -82 -2 l0 8 q42 -12 80 0 z" fill="url(#dvBook)" />
            <rect x="147" y="226" width="6" height="66" rx="3" fill="#0E2E7E" />
            <g stroke="#9DB4E6" strokeWidth="3" strokeLinecap="round">
              <path d="M88 246 h44" /><path d="M88 258 h40" /><path d="M88 270 h44" />
              <path d="M168 246 h44" /><path d="M172 258 h40" /><path d="M168 270 h44" />
            </g>
          </motion.g>

          {/* WINGS — rest at sides, raise to cover eyes, or up to cheer */}
          <motion.g variants={wingL} animate={mode} transition={spring} style={{ transformBox: 'fill-box', transformOrigin: '104px 196px' }}>
            <path d="M104 188 q-40 16 -30 60 q8 26 34 18 q22 -8 16 -44 q-4 -26 -20 -34 z" fill="url(#dvWing)" />
            <path d="M96 208 q-14 20 4 42" stroke="#E39A12" strokeWidth="4" fill="none" strokeLinecap="round" />
          </motion.g>
          <motion.g variants={wingR} animate={mode} transition={spring} style={{ transformBox: 'fill-box', transformOrigin: '196px 196px' }}>
            <path d="M196 188 q40 16 30 60 q-8 26 -34 18 q-22 -8 -16 -44 q4 -26 20 -34 z" fill="url(#dvWing)" />
            <path d="M204 208 q14 20 -4 42" stroke="#E39A12" strokeWidth="4" fill="none" strokeLinecap="round" />
          </motion.g>
        </motion.g>
      </motion.svg>
    </div>
  )
}
