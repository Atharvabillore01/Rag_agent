const BASE = '/api'

function getToken() {
  return localStorage.getItem('duckvault_token')
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

// Fetch a binary attachment (e.g. .docx export) with auth and trigger a browser
// download. Reads the filename from Content-Disposition, falling back if absent.
export async function downloadFile(path, fallbackName = 'download') {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Download failed')
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = cd.match(/filename="?([^"]+)"?/)
  const name = match ? match[1] : fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export const auth = {
  login:    (email, password) => request('POST', '/auth/login',    { email, password }),
  register: (email, password, tenant_name) => request('POST', '/auth/register', { email, password, tenant_name }),
  logout:   () => request('POST', '/auth/logout'),   // G14: server-side token revocation
}

export const documents = {
  list:    (skip = 0, limit = 50, folderId = null) =>
    request('GET', `/documents/?skip=${skip}&limit=${limit}${folderId ? `&folder_id=${encodeURIComponent(folderId)}` : ''}`),
  get:     (id)                   => request('GET', `/documents/${id}`),
  viewUrl: (id)                   => request('GET', `/documents/${id}/view-url`),
  move:    (id, folder_id)        => request('PATCH', `/documents/${id}/folder`, { folder_id }),
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
  // Live ingestion progress via Server-Sent Events. Yields {event_type, status, ...}.
  // Uses fetch (not EventSource) so the Authorization header can be sent.
  async *events(id, signal) {
    const res = await fetch(`${BASE}/documents/${id}/events`, {
      headers: { Authorization: `Bearer ${getToken()}` },
      signal,
    })
    if (!res.ok || !res.body) return
    const reader = res.body.getReader()
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
          try { yield JSON.parse(line.slice(6)) } catch {}
        }
      }
    }
  },
}

export const review = {
  list:           ()            => request('GET',    '/review/'),
  get:            (id)          => request('GET',    `/review/${id}`),
  create:         (data)        => request('POST',   '/review/', data),
  addColumns:     (id, data)    => request('POST',   `/review/${id}/columns`, data),
  suggestColumns: (instruction) => request('POST',   '/review/suggest-columns', { instruction }),
  delete:         (id)          => request('DELETE', `/review/${id}`),
}

export const redline = {
  list:   ()      => request('GET',    '/redline/'),
  get:    (id)    => request('GET',    `/redline/${id}`),
  create: (data)  => request('POST',   '/redline/', data),
  delete: (id)    => request('DELETE', `/redline/${id}`),
}

export const translation = {
  list:   ()      => request('GET',    '/translation/'),
  get:    (id)    => request('GET',    `/translation/${id}`),
  create: (data)  => request('POST',   '/translation/', data),
  delete: (id)    => request('DELETE', `/translation/${id}`),
}

export const lod = {
  list:   ()      => request('GET',    '/lod/'),
  get:    (id)    => request('GET',    `/lod/${id}`),
  create: (data)  => request('POST',   '/lod/', data),
  delete: (id)    => request('DELETE', `/lod/${id}`),
}

export const drafting = {
  list:   ()      => request('GET',    '/drafting/'),
  get:    (id)    => request('GET',    `/drafting/${id}`),
  create: (data)  => request('POST',   '/drafting/', data),
  delete: (id)    => request('DELETE', `/drafting/${id}`),
}

export const folders = {
  list:   ()          => request('GET',    '/folders/'),
  create: (name)      => request('POST',   '/folders/', { name }),
  rename: (id, name)  => request('PATCH',  `/folders/${id}`, { name }),
  delete: (id)        => request('DELETE', `/folders/${id}`),
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
