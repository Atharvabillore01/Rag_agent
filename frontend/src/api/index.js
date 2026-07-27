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

// FastAPI returns `detail` as a string for HTTPException but as an array of
// {loc,msg,type} objects for 422 validation errors. Render both as readable text
// (a raw array would stringify to "[object Object]").
function formatDetail(detail, fallback) {
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail.map(d => (d && d.msg) ? d.msg : String(d)).filter(Boolean)
    return msgs.length ? msgs.join('; ') : fallback
  }
  return fallback
}

async function request(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(formatDetail(err.detail, 'Request failed'))
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

// Voice input: upload a recorded audio blob for transcription. Returns { text }.
export async function transcribeAudio(blob, filename = 'recording.webm') {
  const fd = new FormData()
  fd.append('file', blob, filename)
  const res = await fetch(`${BASE}/transcribe/`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: fd,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Transcription failed')
  }
  return res.json()
}

export const auth = {
  login:         (email, password) => request('POST', '/auth/login',    { email, password }),
  platformLogin: (email, password) => request('POST', '/auth/platform-login', { email, password }),
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
  // Direct-to-MinIO upload: the file bytes go browser -> object storage via a
  // presigned URL (or S3 multipart for large files); the API only signs + verifies.
  // Same signature as before, plus optional onProgress(fraction 0..1).
  upload: async (file, onProgress) => {
    const MULTIPART_THRESHOLD = 8 * 1024 * 1024   // 8 MB
    const PART_SIZE = 8 * 1024 * 1024
    const contentType = file.type || 'application/octet-stream'

    const init = await request('POST', '/documents/upload-init', {
      filename: file.name,
      content_type: contentType,
      multipart: file.size > MULTIPART_THRESHOLD,
    })

    if (init.method === 'single') {
      const put = await fetch(init.upload_url, {
        method: 'PUT', headers: { 'Content-Type': contentType }, body: file,
      })
      if (!put.ok) throw new Error('Upload to storage failed')
      onProgress?.(1)
      return request('POST', `/documents/${init.document_id}/complete`, {})
    }

    // Multipart: slice, sign each part, PUT direct, then complete.
    const parts = []
    const total = Math.ceil(file.size / PART_SIZE)
    for (let i = 0; i < total; i++) {
      const partNumber = i + 1
      const blob = file.slice(i * PART_SIZE, Math.min(file.size, (i + 1) * PART_SIZE))
      const { url } = await request('POST', `/documents/${init.document_id}/multipart/sign-part`,
        { upload_id: init.upload_id, part_number: partNumber })
      const put = await fetch(url, { method: 'PUT', headers: { 'Content-Type': contentType }, body: blob })
      if (!put.ok) {
        await request('POST', `/documents/${init.document_id}/multipart/abort`,
          { upload_id: init.upload_id }).catch(() => {})
        throw new Error(`Upload failed on part ${partNumber}`)
      }
      // Requires MinIO/S3 CORS to expose the ETag header to the browser.
      const etag = put.headers.get('ETag') || put.headers.get('etag')
      parts.push({ PartNumber: partNumber, ETag: etag })
      onProgress?.(partNumber / total)
    }
    return request('POST', `/documents/${init.document_id}/complete`,
      { upload_id: init.upload_id, parts })
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

export const contentions = {
  list:   ()      => request('GET',    '/contentions/'),
  get:    (id)    => request('GET',    `/contentions/${id}`),
  create: (data)  => request('POST',   '/contentions/', data),
  delete: (id)    => request('DELETE', `/contentions/${id}`),
}

export const playbook = {
  list:    ()      => request('GET',    '/playbook/'),
  get:     (id)    => request('GET',    `/playbook/${id}`),
  create:  (data)  => request('POST',   '/playbook/', data),
  delete:  (id)    => request('DELETE', `/playbook/${id}`),
  default: ()      => request('GET',    '/playbook/default'),
}

export const crossExam = {
  list:   ()      => request('GET',    '/cross-exam/'),
  get:    (id)    => request('GET',    `/cross-exam/${id}`),
  create: (data)  => request('POST',   '/cross-exam/', data),
  delete: (id)    => request('DELETE', `/cross-exam/${id}`),
}

export const pii = {
  list:   ()      => request('GET',    '/pii/'),
  get:    (id)    => request('GET',    `/pii/${id}`),
  create: (data)  => request('POST',   '/pii/', data),
  delete: (id)    => request('DELETE', `/pii/${id}`),
}

export const folders = {
  list:   ()          => request('GET',    '/folders/'),
  create: (name)      => request('POST',   '/folders/', { name }),
  rename: (id, name)  => request('PATCH',  `/folders/${id}`, { name }),
  delete: (id)        => request('DELETE', `/folders/${id}`),
}

export const skills = {
  // Pre-built, domain-scoped workflow templates for the caller's tenant.
  list: () => request('GET', '/skills/'),
}

// Platform (super-admin) console — cross-tenant management. Requires a
// platform-admin token; the server enforces via require_platform_admin.
export const platform = {
  listOrgs:     ()              => request('GET',   '/platform/orgs'),
  getOrg:       (id)            => request('GET',   `/platform/orgs/${id}`),
  createOrg:    (data)          => request('POST',  '/platform/orgs', data),
  updateOrg:    (id, data)      => request('PATCH', `/platform/orgs/${id}`, data),
  addMember:    (id, data)      => request('POST',  `/platform/orgs/${id}/members`, data),
  updateMember: (id, uid, data) => request('PATCH', `/platform/orgs/${id}/members/${uid}`, data),
  moveMember:   (id, uid, data) => request('POST',  `/platform/orgs/${id}/members/${uid}/move`, data),
  getRateLimit: (id)            => request('GET',   `/platform/orgs/${id}/rate-limit`),
  setRateLimit: (id, data)      => request('PUT',   `/platform/orgs/${id}/rate-limit`, data),
}

export const clinic = {
  doctors:        ()               => request('GET',    '/clinic/doctors'),
  createDoctor:   (data)           => request('POST',   '/clinic/doctors', data),
  setStatus:      (status)         => request('PATCH',  '/clinic/me/status', { status }),
  listPatients:   (search = '')    => request('GET',    `/clinic/patients?search=${encodeURIComponent(search)}`),
  createPatient:  (data)           => request('POST',   '/clinic/patients', data),
  enqueue:        (data)           => request('POST',   '/clinic/queue', data),
  queue:          (doctorId = '')  => request('GET',    `/clinic/queue${doctorId ? `?doctor_user_id=${doctorId}` : ''}`),
  myQueue:        ()               => request('GET',    '/clinic/me/queue'),
  updateQueue:    (id, status)     => request('PATCH',  `/clinic/queue/${id}`, { status }),
  handoff:        (id, doctor_user_id) => request('POST', `/clinic/queue/${id}/handoff`, { doctor_user_id }),
  followUps:      ()               => request('GET',    '/clinic/follow-ups'),
  createFollowUp: (data)           => request('POST',   '/clinic/follow-ups', data),
  assignments:    ()               => request('GET',    '/clinic/assignments'),
  setAssignment:  (rid, doctor_user_id) => request('PUT', `/clinic/assignments/${rid}`, { doctor_user_id }),
  sendPatientIn:  (data = {})      => request('POST',   '/clinic/send-patient-in', data),
  notifications:  ()               => request('GET',    '/clinic/notifications'),
  markRead:       (id)             => request('POST',   `/clinic/notifications/${id}/read`),
  createVisit:    (data)           => request('POST',   '/clinic/visits', data),
  visits:         (patientId = '') => request('GET',    `/clinic/visits${patientId ? `?patient_id=${patientId}` : ''}`),
  analytics:      ()               => request('GET',    '/clinic/analytics'),
  sharePatient:   (pid, doctor_user_id) => request('POST', `/clinic/patients/${pid}/share`, { doctor_user_id }),
  shares:         (pid)            => request('GET',    `/clinic/patients/${pid}/shares`),
  unshare:        (pid, did)       => request('DELETE', `/clinic/patients/${pid}/shares/${did}`),
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
