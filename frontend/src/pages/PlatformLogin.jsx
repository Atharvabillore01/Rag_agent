import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Mail, Lock, ArrowRight, Eye, EyeOff, Building2, ShieldCheck } from 'lucide-react'
import { auth as authApi } from '../api'
import { useAuthStore } from '../stores/authStore'

// Separate management (platform-admin) sign-in. Hits /auth/platform-login, which
// rejects non-management accounts, and routes into the Platform Console.
export default function PlatformLogin() {
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw]     = useState(false)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')

  const login    = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await authApi.platformLogin(email, password)
      login(res.access_token)
      navigate('/platform')
    } catch (err) {
      setError(err.message || 'Sign in failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-12"
      style={{ background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #1648C0 140%)' }}>
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-sm bg-white rounded-2xl shadow-elevated p-7"
      >
        <div className="flex items-center gap-2.5 mb-6">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #1A56DB 0%, #1648C0 100%)' }}>
            <Building2 size={20} className="text-white" />
          </div>
          <div>
            <p className="font-display font-bold text-duck-navy leading-none">Management Console</p>
            <p className="text-[11px] text-slate-400 mt-1">Platform administrators only</p>
          </div>
        </div>

        <h1 className="text-xl font-display font-bold text-duck-navy mb-1">Management sign-in</h1>
        <p className="text-slate-500 text-sm mb-6">Sign in to manage organizations, members and plans.</p>

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
              <input type="email" className="input-field pl-10" placeholder="you@company.com"
                value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">Password</label>
            <div className="relative">
              <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input type={showPw ? 'text' : 'password'} className="input-field pl-10 pr-10"
                placeholder="Enter your password" value={password}
                onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
              <button type="button" onClick={() => setShowPw(v => !v)} tabIndex={-1}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          <button type="submit" disabled={loading}
            className="btn-primary w-full flex items-center justify-center gap-2 mt-2">
            {loading ? (
              <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Signing in…</>
            ) : (
              <>Sign in to console <ArrowRight size={16} /></>
            )}
          </button>
        </form>

        <div className="mt-6 pt-5 border-t border-slate-100 text-center">
          <p className="text-[11px] text-slate-400 flex items-center justify-center gap-1.5 mb-2">
            <ShieldCheck size={12} className="text-emerald-500" /> Restricted to platform administrators
          </p>
          <Link to="/login" className="text-sm text-duck-blue font-semibold hover:underline">
            Back to workspace sign-in
          </Link>
        </div>
      </motion.div>
    </div>
  )
}
