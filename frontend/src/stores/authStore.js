import { create } from 'zustand'

function parseJwt(token) {
  try {
    return JSON.parse(atob(token.split('.')[1]))
  } catch {
    return null
  }
}

function hydrateUser(token) {
  const raw = parseJwt(token)
  if (!raw) return null
  return {
    id:            raw.sub,
    tenant_id:     raw.tenant_id,
    role:          raw.role,
    email:         raw.email,
    domain:        raw.domain || 'generic',
    is_platform_admin: raw.is_platform_admin === true,
    exp:           raw.exp,
  }
}

export const useAuthStore = create((set) => ({
  token: localStorage.getItem('duckvault_token') || null,
  user:  (() => {
    const t = localStorage.getItem('duckvault_token')
    return t ? hydrateUser(t) : null
  })(),

  login(token) {
    localStorage.setItem('duckvault_token', token)
    set({ token, user: hydrateUser(token) })
  },

  logout() {
    localStorage.removeItem('duckvault_token')
    set({ token: null, user: null })
  },
}))
