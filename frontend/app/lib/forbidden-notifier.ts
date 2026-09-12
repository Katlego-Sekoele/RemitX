/** Lets the query cache signal 403 without reaching for React context. */

type Listener = () => void

let listeners = new Set<Listener>()

export function subscribeForbidden(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function notifyForbidden() {
  for (const listener of listeners) {
    listener()
  }
}
