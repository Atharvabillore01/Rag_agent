import { useEffect, useRef } from 'react'

// Subscribe to the clinic live-event stream (SSE via fetch so the Authorization
// header can be sent). Calls onEvent(evt) for each event; reconnects if the
// stream drops while mounted. onEvent is kept in a ref so re-renders do not
// re-open the connection.
export function useClinicEvents(onEvent) {
  const cb = useRef(onEvent)
  cb.current = onEvent

  useEffect(() => {
    const ctrl = new AbortController()
    let stopped = false

    async function run() {
      while (!stopped) {
        try {
          const res = await fetch('/api/clinic/events', {
            headers: { Authorization: `Bearer ${localStorage.getItem('duckvault_token')}` },
            signal: ctrl.signal,
          })
          if (!res.ok || !res.body) { await wait(3000); continue }
          const reader = res.body.getReader()
          const decoder = new TextDecoder()
          let buffer = ''
          while (!stopped) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            const chunks = buffer.split('\n\n')
            buffer = chunks.pop()
            for (const chunk of chunks) {
              const line = chunk.split('\n').find(l => l.startsWith('data: '))
              if (line) {
                try { cb.current(JSON.parse(line.slice(6))) } catch { /* ignore */ }
              }
            }
          }
        } catch {
          if (stopped) break
        }
        await wait(2000)   // brief backoff before reconnecting
      }
    }
    function wait(ms) { return new Promise(r => setTimeout(r, ms)) }

    run()
    return () => { stopped = true; ctrl.abort() }
  }, [])
}
