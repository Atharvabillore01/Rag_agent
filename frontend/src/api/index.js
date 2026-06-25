const BASE = '/api'

function getToken() {
  return localStorage.getItem('ida_token')
}

function headers(extra = {}) {
  const h = { 'Content-Type': 'application/json', ...extra }
  const tok = getToken()
  if (tok) h['Authorization'] = `Bearer ${tok}`
  return h
}

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  if (res.status === 204) return null
  return res.json()
}

export const auth = {
  login:    (email, password) => request('POST', '/auth/login',    { email, password }),
  register: (email, password, tenant_name) => request('POST', '/auth/register', { email, password, tenant_name }),
}

export const documents = {
  list:    (skip = 0, limit = 50) => request('GET', `/documents/?skip=${skip}&limit=${limit}`),
  get:     (id)                   => request('GET', `/documents/${id}`),
  viewUrl: (id)                   => request('GET', `/documents/${id}/view-url`),
  delete:  (id)                   => request('DELETE', `/documents/${id}`),
  upload: async (file) => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`${BASE}/documents/upload`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}` },
      body: fd,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || 'Upload failed')
    }
    return res.json()
  },
}

export const admin = {
  listUsers:      ()                           => request('GET',   '/admin/users'),
  createUser:     (data)                       => request('POST',  '/admin/users', data),
  updateRole:     (userId, role)               => request('PATCH', `/admin/users/${userId}/role`, { role }),
  auditLog:       (skip=0, limit=100)          => request('GET',   `/admin/audit-log?skip=${skip}&limit=${limit}`),
  tenant:         ()                           => request('GET',   '/admin/tenant'),
  observability:  (action='', userId='', skip=0, limit=200) => {
    const p = new URLSearchParams({ skip, limit })
    if (action) p.set('action', action)
    if (userId) p.set('user_id', userId)
    return request('GET', `/admin/observability?${p}`)
  },
}

export async function* streamQuery(question, collection_tags) {
  const res = await fetch(`${BASE}/query/stream`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ question, collection_tags }),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Stream failed')
  }

  const queryId = res.headers.get('X-Query-Id')
  const reader  = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6))
          yield { ...event, queryId }
        } catch {}
      }
    }
  }
}
