import { useState } from "react"

/**
 * A number that goes up each time `open` turns true. Key a dialog's body on
 * it so every opening starts from a clean slate, while the body stays mounted
 * through the closing animation.
 */
export function useOpenSession(open: boolean): number {
  const [session, setSession] = useState(0)
  const [wasOpen, setWasOpen] = useState(open)
  // Adjusting state while rendering, when a prop changes: React re-renders
  // straight away, before anything is painted with the stale key.
  if (open !== wasOpen) {
    setWasOpen(open)
    if (open) setSession((value) => value + 1)
  }
  return session
}
