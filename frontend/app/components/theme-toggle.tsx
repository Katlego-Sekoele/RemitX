"use client"

import { MonitorIcon, MoonIcon, SunIcon } from "@phosphor-icons/react"
import { useTheme } from "next-themes"
import { useCallback, useEffect, useState } from "react"

import { Button } from "~/components/ui/button"
import { cn } from "~/lib/utils"

type ThemeValue = "light" | "dark" | "system"

type ThemeOption = {
  value: ThemeValue
  label: string
  icon: typeof SunIcon
}

const themeOptions: ThemeOption[] = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "Auto", icon: MonitorIcon },
]

export function useThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const activeTheme = (theme ?? "system") as ThemeValue
  const activeOption =
    themeOptions.find((option) => option.value === activeTheme) ??
    themeOptions[2]

  const cycleTheme = useCallback(() => {
    const index = themeOptions.findIndex(
      (option) => option.value === activeTheme
    )
    const next = themeOptions[(index + 1) % themeOptions.length]
    setTheme(next.value)
  }, [activeTheme, setTheme])

  return { mounted, activeTheme, activeOption, setTheme, cycleTheme }
}

function ThemeToggleSkeleton({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <Button variant="ghost" size="icon-sm" disabled aria-hidden>
        <SunIcon weight="bold" />
      </Button>
    )
  }

  return (
    <div
      aria-hidden
      className="inline-flex overflow-hidden rounded-md border border-border bg-background"
    >
      {themeOptions.map((option) => (
        <Button
          key={option.value}
          variant="ghost"
          size="icon-sm"
          disabled
          className="rounded-none"
        >
          <option.icon weight="bold" />
        </Button>
      ))}
    </div>
  )
}

export function ThemeToggle() {
  const { mounted, activeTheme, setTheme } = useThemeToggle()

  if (!mounted) {
    return <ThemeToggleSkeleton />
  }

  return (
    <div
      role="group"
      aria-label="Theme"
      className="inline-flex overflow-hidden rounded-md border border-border bg-background"
    >
      {themeOptions.map(({ value, label, icon: Icon }) => {
        const isActive = activeTheme === value

        return (
          <Button
            key={value}
            variant={isActive ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label={label}
            aria-pressed={isActive}
            onClick={() => setTheme(value)}
            className={cn("rounded-none", !isActive && "text-muted-foreground")}
          >
            <Icon weight="bold" />
          </Button>
        )
      })}
    </div>
  )
}

type ThemeToggleCycleProps = {
  className?: string
}

/** Single button that cycles light → dark → auto. */
export function ThemeToggleCycle({ className }: ThemeToggleCycleProps) {
  const { mounted, activeOption, cycleTheme } = useThemeToggle()
  const Icon = activeOption.icon

  if (!mounted) {
    return <ThemeToggleSkeleton compact />
  }

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      className={className}
      aria-label={`Theme: ${activeOption.label}. Click to switch theme.`}
      onClick={cycleTheme}
    >
      <Icon weight="bold" />
    </Button>
  )
}
