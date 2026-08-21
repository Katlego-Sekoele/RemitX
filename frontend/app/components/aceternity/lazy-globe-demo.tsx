import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react"

import { cn } from "~/lib/utils"

const GlobeDemo = lazy(() => import("~/components/aceternity/globe-demo"))

type LazyGlobeDemoProps = {
  className?: string
}

function canUseWebGL(): boolean {
  if (typeof document === "undefined") return false
  try {
    const canvas = document.createElement("canvas")
    return !!(
      canvas.getContext("webgl2") ||
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl")
    )
  } catch {
    return false
  }
}

class GlobeErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.warn("Globe failed to render; showing fallback.", error, info)
  }

  render() {
    if (this.state.failed) return this.props.fallback
    return this.props.children
  }
}

function GlobePlaceholder({ className }: { className?: string }) {
  return (
    <div
      className={cn("size-full bg-muted/40", className)}
      aria-hidden="true"
    />
  )
}

/**
 * Defers the ~2MB three.js chunk until the hero is near the viewport, and
 * skips WebGL entirely when the browser cannot create a context (headless /
 * broken GPU) so Lighthouse and low-end clients do not throw.
 */
export function LazyGlobeDemo({ className }: LazyGlobeDemoProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [shouldLoad, setShouldLoad] = useState(false)
  const [webglOk, setWebglOk] = useState(false)

  useEffect(() => {
    setWebglOk(canUseWebGL())
  }, [])

  useEffect(() => {
    if (!webglOk) return
    const node = hostRef.current
    if (!node) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setShouldLoad(true)
          observer.disconnect()
        }
      },
      { rootMargin: "200px 0px", threshold: 0.01 }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [webglOk])

  return (
    <div
      ref={hostRef}
      className={cn("relative size-full overflow-visible", className)}
    >
      {!webglOk || !shouldLoad ? (
        <GlobePlaceholder />
      ) : (
        <GlobeErrorBoundary fallback={<GlobePlaceholder />}>
          <Suspense fallback={<GlobePlaceholder />}>
            {/*
              Oversized canvas: globe reads large in the layout slot while the
              atmosphere still has room inside the WebGL frame (no edge clip).
            */}
            <div className="pointer-events-none absolute top-1/2 left-1/2 aspect-square w-[138%] -translate-x-1/2 -translate-y-1/2">
              <GlobeDemo />
            </div>
          </Suspense>
        </GlobeErrorBoundary>
      )}
    </div>
  )
}
