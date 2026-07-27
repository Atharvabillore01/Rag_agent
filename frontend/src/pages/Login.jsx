import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Mail, Lock, ArrowRight, Eye, EyeOff } from 'lucide-react'
import { auth as authApi } from '../api'
import { useAuthStore } from '../stores/authStore'
import DuckVaultLogo from '../components/DuckVaultLogo'
import DuckScene3D from '../components/DuckScene3D'

export default function Login() {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw]       = useState(false)
  const [pwFocus, setPwFocus]     = useState(false)
  const [emailFocus, setEmailFocus] = useState(false)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')

  const login    = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  // Duck zooms in while you fill the form: hides its eyes for the password
  // (peeks if revealed), just watches while you type your email.
  const duckExpr = pwFocus ? (showPw ? 'peek' : 'cover') : emailFocus ? 'watch' : null

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await authApi.login(email, password)
      login(res.access_token)
      // Clinic-vertical users land in the full-screen clinic area, not the doc app.
      const u = useAuthStore.getState().user
      navigate(u?.domain === 'clinic' ? '/clinic' : '/chat')
    } catch (err) {
      setError(err.message || 'Invalid credentials. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex">

      {/* ── LEFT PANEL — grass field with the duck companion ── */}
      <div className="hidden lg:flex lg:w-[55%] relative overflow-hidden">
        <DuckScene3D expression={duckExpr} />

        <div className="relative z-10 flex flex-col w-full px-12 pt-9 pb-8 pointer-events-none">
          <DuckVaultLogo size="md" white />
          <div className="mt-14 max-w-md" style={{ textShadow: '0 2px 14px rgba(6,24,14,0.5)' }}>
            <h2 className="text-white font-display font-bold text-4xl leading-tight mb-3">
              Your team's knowledge, one question away.
            </h2>
            <p className="text-white/70 text-sm leading-relaxed">
              Upload contracts, notices, filings and reports — then ask in plain language.
              DuckVault reads, cites, translates, and drafts alongside you.
            </p>
            <p className="text-white/55 text-xs mt-3">
              {duckExpr === 'cover'
                ? "…the duck's covering its eyes so it can't see your password. 🙈"
                : duckExpr === 'peek'
                ? '…okay, it peeked. 👀'
                : "Move your mouse — the duck follows. Idle, it reads a book. 🦆"}
            </p>
          </div>
          <p className="mt-auto text-white/40 text-[11px]">© {new Date().getFullYear()} DuckVault · Secure AI document intelligence</p>
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
          <div className="lg:hidden mb-8">
            <DuckVaultLogo size="sm" />
          </div>

          <h1 className="text-2xl font-display font-bold text-duck-navy mb-1">Welcome back</h1>
          <p className="text-slate-500 text-sm mb-8">Sign in to your DuckVault workspace</p>

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
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  onFocus={() => setEmailFocus(true)}
                  onBlur={() => setEmailFocus(false)}
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
                  onFocus={() => setPwFocus(true)}
                  onBlur={() => setPwFocus(false)}
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
              <Link to="/register" className="text-duck-blue font-semibold hover:underline">
                Register here
              </Link>
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
