"use client"

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type MouseEvent,
  type ReactNode,
  type SetStateAction,
} from "react"

import { cn } from "~/lib/utils"

const MouseEnterContext = createContext<
  [boolean, Dispatch<SetStateAction<boolean>>] | undefined
>(undefined)

type CardContainerProps = {
  children?: ReactNode
  className?: string
  containerClassName?: string
}

export function CardContainer({
  children,
  className,
  containerClassName,
}: CardContainerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [isMouseEntered, setIsMouseEntered] = useState(false)

  function handleMouseMove(event: MouseEvent<HTMLDivElement>) {
    if (!containerRef.current) return
    const {
      left,
      top: offsetTop,
      width,
      height,
    } = containerRef.current.getBoundingClientRect()
    const rotateY = (event.clientX - left - width / 2) / 25
    const rotateX = (event.clientY - offsetTop - height / 2) / 25
    containerRef.current.style.transform = `rotateY(${rotateY}deg) rotateX(${-rotateX}deg)`
  }

  function handleMouseLeave() {
    if (!containerRef.current) return
    setIsMouseEntered(false)
    containerRef.current.style.transform = "rotateY(0deg) rotateX(0deg)"
  }

  return (
    <MouseEnterContext.Provider value={[isMouseEntered, setIsMouseEntered]}>
      <div
        className={cn(
          "flex items-center justify-center py-20",
          containerClassName
        )}
        style={{ perspective: "1000px" }}
      >
        <div
          ref={containerRef}
          onMouseEnter={() => setIsMouseEntered(true)}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          className={cn(
            "relative flex items-center justify-center transition-all duration-200 ease-linear",
            className
          )}
          style={{ transformStyle: "preserve-3d" }}
        >
          {children}
        </div>
      </div>
    </MouseEnterContext.Provider>
  )
}

type CardBodyProps = {
  children: ReactNode
  className?: string
}

export function CardBody({ children, className }: CardBodyProps) {
  return (
    <div
      className={cn(
        "h-96 w-96 [transform-style:preserve-3d] [&>*]:[transform-style:preserve-3d]",
        className
      )}
    >
      {children}
    </div>
  )
}

type CardItemProps = {
  children: ReactNode
  className?: string
  translateX?: number | string
  translateY?: number | string
  translateZ?: number | string
  rotateX?: number | string
  rotateY?: number | string
  rotateZ?: number | string
}

export function CardItem({
  children,
  className,
  translateX = 0,
  translateY = 0,
  translateZ = 0,
  rotateX = 0,
  rotateY = 0,
  rotateZ = 0,
}: CardItemProps) {
  const itemRef = useRef<HTMLDivElement>(null)
  const [isMouseEntered] = useMouseEnter()

  useEffect(() => {
    if (!itemRef.current) return
    if (isMouseEntered) {
      itemRef.current.style.transform = `translateX(${translateX}px) translateY(${translateY}px) translateZ(${translateZ}px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) rotateZ(${rotateZ}deg)`
    } else {
      itemRef.current.style.transform =
        "translateX(0px) translateY(0px) translateZ(0px) rotateX(0deg) rotateY(0deg) rotateZ(0deg)"
    }
  }, [
    isMouseEntered,
    translateX,
    translateY,
    translateZ,
    rotateX,
    rotateY,
    rotateZ,
  ])

  return (
    <div
      ref={itemRef}
      className={cn("w-fit transition duration-200 ease-linear", className)}
    >
      {children}
    </div>
  )
}

export function useMouseEnter() {
  const context = useContext(MouseEnterContext)
  if (context === undefined) {
    throw new Error("useMouseEnter must be used within a CardContainer")
  }
  return context
}
