import { Story, useOf } from "@storybook/addon-docs/blocks"
import {
  AppWindowIcon,
  ArrowSquareOutIcon,
  CircleIcon,
} from "@phosphor-icons/react"
import type { ComponentProps } from "react"

import { GridBackground } from "~/components/aceternity/grid-background"
import { Card, CardAction, CardHeader, CardTitle } from "~/components/ui/card"
import { graph } from "./graph.ts"
import { DocLink } from "./link.tsx"

/** Story exports, as `import * as Stories from "./x.stories"` gives them. */
export type StoryExport = ComponentProps<typeof Story>["of"]

/**
 * A live screen on a docs page, framed as the app it is: a window bar naming
 * the component and story, over the grid the screen is drawn on. The docs
 * around it are plain text and lines, so the product is the only thing in a
 * window. Its code is on the component's own page.
 */
export function ScreenFrame({ of }: { of: StoryExport }) {
  const resolved = useOf(of, ["story"])
  const story = resolved.type === "story" ? resolved.story : undefined
  const component = story
    ? Object.values(graph.components).find((info) =>
        info.stories.some((s) => s.id === story.id)
      )
    : undefined
  return (
    <Card size="sm" className="sb-unstyled gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardTitle className="flex items-center gap-2">
          <span aria-hidden className="flex gap-1 text-muted-foreground/40">
            <CircleIcon weight="fill" className="size-2" />
            <CircleIcon weight="fill" className="size-2" />
            <CircleIcon weight="fill" className="size-2" />
          </span>
          <AppWindowIcon aria-hidden className="ml-2" />
          {component?.name ?? story?.title}
          <span className="font-normal text-muted-foreground">
            {story?.name}
          </span>
        </CardTitle>
        {story && (
          <CardAction>
            <DocLink to={{ story: story.id }} className="text-xs">
              Open
              <ArrowSquareOutIcon aria-hidden />
            </DocLink>
          </CardAction>
        )}
      </CardHeader>
      <GridBackground className="min-h-0 bg-muted/40 p-6">
        {/* The app's own page colour: components with no background of
            their own (an outline Item) must not show the grid through. */}
        <div className="mx-auto w-full max-w-2xl rounded-lg bg-background p-4">
          <Story of={of} />
        </div>
      </GridBackground>
    </Card>
  )
}
