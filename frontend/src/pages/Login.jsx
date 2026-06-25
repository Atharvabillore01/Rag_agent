import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Mail, Lock, ArrowRight, Eye, EyeOff } from 'lucide-react'
import { auth as authApi } from '../api'
import { useAuthStore } from '../stores/authStore'
import IDALogo from '../components/IDALogo'

const PROJECTS = [
  { name: 'Lata Mangeshkar Auditorium',  type: 'Cultural & Community',    img: 'https://www.idaindore.org/Content/img/slider/Lata-Mangeshkar.jpg' },
  { name: 'ISBT MR-10 Bus Terminal',     type: 'Transport Infrastructure', img: 'https://www.idaindore.org/Content/img/slider/ISBT-MR10_3.jpg' },
  { name: 'Khajrana Flyover',            type: 'Road Infrastructure',      img: 'https://www.idaindore.org/Content/img/slider/KHAJRANA-FLYOVER.jpg' },
  { name: 'Bhawarkua Development',       type: 'Urban Development',        img: 'https://www.idaindore.org/Content/img/slider/bhawarkua.jpg' },
  { name: 'Nayata Mindla Project',       type: 'Residential Scheme',       img: 'https://www.idaindore.org/Content/img/slider/NAYATA-MINDLA_2.jpg' },
]

const LEADERS = [
  { name: 'Dr. Mohan Yadav',            shortName: 'Dr. Mohan Yadav',      role: "Hon'ble Chief Minister, MP",          img: 'https://www.idaindore.org/assets/img/CM_mohan_yadav.png' },
  { name: 'Shri Kailash Vijayvargiya',  shortName: 'Kailash Vijayvargiya', role: 'Minister, Urban Development',         img: 'https://www.idaindore.org/assets/img/kailashvijaybargi.png' },
  { name: 'Dr. Sudam P. Khade, IAS',   shortName: 'Dr. Sudam Khade',      role: 'Chairman, IDA',                       img: 'https://www.idaindore.org/assets/img/Chairman_Sudam_Pandharinath.png' },
  { name: 'Dr. Parikshit S. Zade, IAS', shortName: 'Dr. Parikshit Zade',  role: 'CEO, Indore Dev. Authority',          img: 'https://www.idaindore.org/assets/img/CEO_Parikshit_Sanjayrao.png' },
]

export default function Login() {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw]     = useState(false)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const [current, setCurrent]   = useState(0)

  const login    = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  useEffect(() => {
    const t = setInterval(() => setCurrent(c => (c + 1) % PROJECTS.length), 5000)
    return () => clearInterval(t)
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await authApi.login(email, password)
      login(res.access_token)
      navigate('/chat')
    } catch (err) {
      setError(err.message || 'Invalid credentials. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const proj = PROJECTS[current]

  return (
    <div className="min-h-screen flex">

      {/* ── LEFT PANEL — image fills top, leaders sit below ── */}
      <div className="hidden lg:flex lg:w-[58%] flex-col overflow-hidden">

        {/* TOP: Full-bleed rotating property image */}
        <div className="flex-1 relative overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.img
              key={current}
              src={proj.img}
              alt={proj.name}
              initial={{ opacity: 0, scale: 1.06 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 1.1, ease: 'easeInOut' }}
              className="absolute inset-0 w-full h-full object-cover"
            />
          </AnimatePresence>

          {/* Gradient — dark at top for logo, dark at bottom for project name */}
          <div className="absolute inset-0"
            style={{ background: 'linear-gradient(to bottom, rgba(10,28,60,0.78) 0%, rgba(10,28,60,0.05) 40%, rgba(10,28,60,0.05) 60%, rgba(10,28,60,0.75) 100%)' }} />

          {/* IDA Logo + MP badge */}
          <div className="absolute top-0 left-0 right-0 flex items-center justify-between px-9 pt-8">
            <IDALogo size="md" white />
            <div className="flex items-center gap-2 bg-white/10 backdrop-blur-sm border border-white/20 rounded-full px-3 py-1.5">
              <div className="w-2 h-2 rounded-full bg-green-400" />
              <span className="text-white text-[11px] font-medium">Govt. of Madhya Pradesh</span>
            </div>
          </div>

          {/* Project name + dots at bottom of image */}
          <div className="absolute bottom-0 left-0 right-0 px-9 pb-7">
            <AnimatePresence mode="wait">
              <motion.div
                key={current}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                transition={{ duration: 0.4 }}
              >
                <p className="text-white/50 text-[10px] font-semibold uppercase tracking-widest mb-1">
                  {proj.type}
                </p>
                <p className="text-white font-display font-bold text-xl leading-tight mb-3">
                  {proj.name}
                </p>
              </motion.div>
            </AnimatePresence>

            <div className="flex gap-1.5">
              {PROJECTS.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setCurrent(i)}
                  className={`rounded-full transition-all duration-300 ${
                    i === current ? 'w-6 h-1.5 bg-white' : 'w-1.5 h-1.5 bg-white/35 hover:bg-white/60'
                  }`}
                />
              ))}
            </div>
          </div>
        </div>

        {/* BOTTOM: Leadership section — solid dark navy, no boxes */}
        <div className="bg-ida-navy px-9 pt-7 pb-8 flex-shrink-0">
          <p className="text-white/40 text-[10px] font-semibold uppercase tracking-[0.18em] mb-5">
            Our Leadership
          </p>

          <div className="grid grid-cols-4 gap-4">
            {LEADERS.map((leader, i) => (
              <motion.div
                key={leader.name}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 + i * 0.07 }}
                className="flex flex-col items-center gap-3"
              >
                {/* Photo */}
                <div className="relative w-24 h-24 rounded-2xl overflow-hidden flex-shrink-0
                                shadow-[0_4px_20px_rgba(0,0,0,0.4)] border-2 border-white/20">
                  <img
                    src={leader.img}
                    alt={leader.name}
                    className="w-full h-full object-cover object-top"
                    onError={e => {
                      e.currentTarget.parentElement.style.background = 'rgba(255,255,255,0.08)'
                      e.currentTarget.style.display = 'none'
                    }}
                  />
                  {/* Saffron bottom accent */}
                  <div className="absolute bottom-0 left-0 right-0 h-1 bg-ida-saffron opacity-80" />
                </div>

                {/* Name + role */}
                <div className="text-center">
                  <p className="text-white text-xs font-semibold leading-snug">
                    {leader.shortName}
                  </p>
                  <p className="text-white/45 text-[10px] leading-tight mt-0.5 line-clamp-2">
                    {leader.role.split(',')[0]}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>

          <div className="border-t border-white/10 mt-5 pt-4 flex items-center justify-between">
            <p className="text-white/65 text-[11px] font-semibold font-display">
              "जहाँ निरन्तर निर्माण ही लक्ष्य है"
            </p>
            <p className="text-white/30 text-[10px]">IDA Indore · Est. 1973</p>
          </div>
        </div>
      </div>

      {/* ── RIGHT PANEL — login form ── */}
      <div className="flex-1 flex items-center justify-center bg-white px-6 py-12">
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-sm"
        >
          {/* Mobile logo */}
          <div className="lg:hidden mb-8">
            <IDALogo size="sm" />
          </div>

          <h1 className="text-2xl font-display font-bold text-ida-navy mb-1">Welcome back</h1>
          <p className="text-slate-500 text-sm mb-8">Sign in to your IDA Knowledge Assistant</p>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-5 flex items-center gap-2 bg-red-50 border border-red-100 rounded-xl px-4 py-3 text-sm text-red-600"
            >
              <div className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
              {error}
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Email address</label>
              <div className="relative">
                <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="email"
                  className="input-field pl-10"
                  placeholder="you@idaindore.org"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Password</label>
              <div className="relative">
                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type={showPw ? 'text' : 'password'}
                  className="input-field pl-10 pr-10"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(v => !v)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  tabIndex={-1}
                >
                  {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2 mt-2"
            >
              {loading ? (
                <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Signing in…</>
              ) : (
                <>Sign In <ArrowRight size={16} /></>
              )}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-slate-100 text-center">
            <p className="text-sm text-slate-500">
              Don't have an account?{' '}
              <Link to="/register" className="text-ida-blue font-semibold hover:underline">
                Register here
              </Link>
            </p>
          </div>

          {/* Gov badge */}
          <div className="mt-8 flex items-center justify-center gap-2.5 opacity-50">
            <img
              src="https://www.idaindore.org/assets/img/logo.png"
              alt="IDA Seal"
              className="h-6 w-auto object-contain grayscale"
            />
            <span className="text-[10px] text-slate-500 font-medium tracking-wide">
              Government of Madhya Pradesh
            </span>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
