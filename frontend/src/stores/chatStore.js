import { create } from 'zustand'
import { persist } from 'zustand/middleware'

function makeSessionId() {
  return `sess_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
}

export const useChatStore = create(
  persist(
    (set, get) => ({
      // ── Persisted ─────────────────────────────────────────────────────────
      sessions: {},          // Record<sessionId, { id, title, messages, createdAt }>
      currentSessionId: null,

      // ── In-memory only (not persisted) ────────────────────────────────────
      streaming: false,
      statusSteps: [],       // pipeline step visibility
      thoughts: [],          // planner / verifier reasoning

      // ── Derived helpers ────────────────────────────────────────────────────
      currentMessages() {
        const { sessions, currentSessionId } = get()
        if (!currentSessionId || !sessions[currentSessionId]) return []
        return sessions[currentSessionId].messages
      },

      sortedSessions() {
        return Object.values(get().sessions).sort((a, b) => b.createdAt - a.createdAt)
      },

      ensureSession() {
        const { currentSessionId, sessions } = get()
        if (currentSessionId && sessions[currentSessionId]) return currentSessionId
        return get().newSession()
      },

      // ── Session management ─────────────────────────────────────────────────
      newSession() {
        const id = makeSessionId()
        set(s => ({
          sessions: {
            ...s.sessions,
            [id]: { id, title: 'New Chat', messages: [], createdAt: Date.now() },
          },
          currentSessionId: id,
          statusSteps: [],
          thoughts: [],
          streaming: false,
        }))
        return id
      },

      switchSession(id) {
        set({ currentSessionId: id, statusSteps: [], thoughts: [], streaming: false })
      },

      deleteSession(id) {
        set(s => {
          const sessions = { ...s.sessions }
          delete sessions[id]
          const remaining = Object.values(sessions).sort((a, b) => b.createdAt - a.createdAt)
          return {
            sessions,
            currentSessionId: remaining[0]?.id ?? null,
            statusSteps: [],
            thoughts: [],
          }
        })
      },

      _patchSession(updater) {
        set(s => {
          const sid = s.currentSessionId
          if (!sid || !s.sessions[sid]) return s
          return { sessions: { ...s.sessions, [sid]: updater(s.sessions[sid]) } }
        })
      },

      // ── Message operations ─────────────────────────────────────────────────
      addUserMessage(text) {
        get().ensureSession()
        get()._patchSession(sess => ({
          ...sess,
          title: sess.messages.length === 0 ? text.slice(0, 45) : sess.title,
          messages: [...sess.messages, { id: Date.now(), role: 'user', text }],
        }))
      },

      startAssistantMessage(id) {
        set({ streaming: true, statusSteps: [], thoughts: [] })
        get()._patchSession(sess => ({
          ...sess,
          messages: [
            ...sess.messages,
            { id, role: 'assistant', text: '', citations: [], followups: [], status: 'streaming' },
          ],
        }))
      },

      appendToken(id, token) {
        get()._patchSession(sess => ({
          ...sess,
          messages: sess.messages.map(m => m.id === id ? { ...m, text: m.text + token } : m),
        }))
      },

      addCitation(id, citation) {
        get()._patchSession(sess => ({
          ...sess,
          messages: sess.messages.map(m =>
            m.id === id ? { ...m, citations: [...m.citations, citation] } : m
          ),
        }))
      },

      finalizeMessage(id, answer, citations, followups = []) {
        const now = Date.now()
        set(s => ({
          streaming: false,
          statusSteps: s.statusSteps.map(step => ({
            ...step,
            done: true,
            elapsed_ms: step.elapsed_ms ?? (now - step.startedAt),
          })),
        }))
        get()._patchSession(sess => ({
          ...sess,
          messages: sess.messages.map(m =>
            m.id === id ? { ...m, text: answer, citations, followups, status: 'done' } : m
          ),
        }))
      },

      setError(id, msg) {
        set({ streaming: false })
        get()._patchSession(sess => ({
          ...sess,
          messages: sess.messages.map(m =>
            m.id === id ? { ...m, text: msg, status: 'error' } : m
          ),
        }))
      },

      // ── Pipeline visibility ────────────────────────────────────────────────
      pushStatus(message) {
        const now = Date.now()
        set(s => {
          const closed = s.statusSteps.map((step, i) =>
            i === s.statusSteps.length - 1 && !step.done
              ? { ...step, done: true, elapsed_ms: now - step.startedAt }
              : step
          )
          return { statusSteps: [...closed, { message, done: false, id: now, startedAt: now }] }
        })
      },

      pushThought(message) {
        set(s => ({ thoughts: [...s.thoughts, { message, id: Date.now() }] }))
      },

      clearHistory() {
        get()._patchSession(sess => ({ ...sess, messages: [] }))
        set({ statusSteps: [], thoughts: [], streaming: false })
      },
    }),
    {
      name: 'rag-chat-sessions',
      partialize: state => ({
        sessions: state.sessions,
        currentSessionId: state.currentSessionId,
      }),
    }
  )
)
