import { Fragment, type ComponentType, type ReactNode } from "react"

/**
 * OpenAPI descriptions are Markdown, and the API's docstrings use little of
 * it: paragraphs and `code`. Enough to render those without a Markdown
 * dependency; anything else shows as written. Each paragraph renders as
 * `paragraph`, so a page header can keep its own description style.
 */
export function Prose({
  text,
  paragraph: Paragraph = "p",
}: {
  text?: string
  paragraph?: ComponentType<{ children: ReactNode }> | "p"
}) {
  if (!text) return null
  return text.split(/\n\s*\n/).map((paragraph, i) => (
    <Paragraph key={i}>
      {paragraph.split(/(`[^`]+`)/).map((part, j) =>
        part.length > 2 && part.startsWith("`") && part.endsWith("`") ? (
          <code key={j} className="font-mono">
            {part.slice(1, -1)}
          </code>
        ) : (
          <Fragment key={j}>{part}</Fragment>
        )
      )}
    </Paragraph>
  ))
}
