import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Mail, Lock, Building2, ArrowRight, Eye, EyeOff } from 'lucide-react'
import { auth as authApi } from '../api'
import { useAuthStore } from '../stores/authStore'
import DuckVaultLogo from '../components/DuckVaultLogo'
import DuckScene3D from '../components/DuckScene3D'

export default function Register() {
  const [form, setForm]       = useState({ email: '', password: '', tenant_name: '' })
  const [showPw, setShowPw]   = useState(false)
  const [pwFocus, setPwFocus] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  // Tell the duck what to do: hide its eyes while a password is being typed
  // (peek instead if the password is revealed).
  const duckExpr = pwFocus ? (showPw ? 'peek' : 'cover') : null
  const login    = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function handleSubmit(e) {
    e.preventDefault()
    if (form.password.length < 6) { setError('Password must be at least 6 characters.'); return }
    setError('')
    setLoading(true)
    try {
      const res = await authApi.register(form.email, form.password, form.tenant_name)
      login(res.access_token)
      navigate('/chat')
    } catch (err) {
      setError(err.message || 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* LEFT PANEL — cozy grass field with a roaming duck */}
      <div className="hidden lg:flex lg:w-[58%] relative overflow-hidden">
        <DuckScene3D expression={duckExpr} guide />

        {/* content overlaid on the scene (top area, where the sky is darkest) */}
        <div className="relative z-10 flex flex-col w-full px-10 pt-8 pb-10 pointer-events-none">
          <DuckVaultLogo size="sm" white />
          <div className="mt-14 max-w-md"
            style={{ textShadow: '0 2px 14px rgba(6,24,14,0.45)' }}>
            <h2 className="text-3xl font-display font-bold text-white mb-2 leading-tight">Join DuckVault</h2>
            <p className="text-white/75 text-sm leading-relaxed">
              Create your organization workspace to start turning documents into answers, drafts, and insights.
            </p>
            <p className="text-white/55 text-xs mt-3">
              {duckExpr === 'cover'
                ? "…the duck's covering its eyes so it can't see your password. 🙈"
                : duckExpr === 'peek'
                ? '…okay, it peeked. 👀'
                : 'Move your mouse — the duck will waddle over. 🦆'}
            </p>
          </div>
        </div>
      </div>

      {/* RIGHT PANEL */}
      <div className="flex-1 flex items-center justify-center bg-white px-6 py-12">
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          className="w-full max-w-sm"
        >
          <div className="lg:hidden mb-8"><DuckVaultLogo size="sm" /></div>

          <h1 className="text-2xl font-display font-bold text-duck-navy mb-1">Create account</h1>
          <p className="text-slate-500 text-sm mb-8">Set up your DuckVault organization workspace</p>

          {error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              className="mb-5 flex items-center gap-2 bg-red-50 border border-red-100 rounded-xl px-4 py-3 text-sm text-red-600">
              <div className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
              {error}
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Organization name</label>
              <div className="relative">
                <Building2 size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input type="text" className="input-field pl-10"
                  placeholder="e.g. Acme Legal LLP"
                  value={form.tenant_name} onChange={set('tenant_name')} required />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Email address</label>
              <div className="relative">
                <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input type="email" className="input-field pl-10"
                  placeholder="admin@company.com"
                  value={form.email} onChange={set('email')} required />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1.5">Password</label>
              <div className="relative">
                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input type={showPw ? 'text' : 'password'} className="input-field pl-10 pr-10"
                  placeholder="Minimum 6 characters"
                  value={form.password} onChange={set('password')} required
                  onFocus={() => setPwFocus(true)} onBlur={() => setPwFocus(false)} />
                <button type="button" tabIndex={-1}
                  onClick={() => setShowPw((v) => !v)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                  {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2 mt-2">
              {loading ? (
                <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Creating account…</>
              ) : (
                <>Create Account <ArrowRight size={16} /></>
              )}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-slate-100 text-center">
            <p className="text-sm text-slate-500">
              Already have an account?{' '}
              <Link to="/login" className="text-duck-blue font-semibold hover:underline">Sign in</Link>
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
