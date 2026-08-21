"use client"

import { MonitorIcon, MoonIcon, SunIcon } from "@phosphor-icons/react"
import { useTheme } from "next-themes"
import { useEffect, useState } from "react"

import { Button } from "~/components/ui/button"
import { cn } from "~/lib/utils"

type ThemeOption = {
  value: "light" | "dark" | "system"
  label: string
  icon: typeof SunIcon
}

const themeOptions: ThemeOption[] = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "Auto", icon: MonitorIcon },
]

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) {
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

  const activeTheme = theme ?? "system"

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
