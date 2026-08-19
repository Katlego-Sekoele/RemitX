import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowClockwise, PaperPlaneTilt, Warning } from "@phosphor-icons/react"
import { useRef, useState } from "react"

import { FadeIn } from "~/components/aceternity/fade-in"
import { GridBackground } from "~/components/aceternity/grid-background"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import { Input } from "~/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { cn } from "~/lib/utils"
import type { Route } from "./+types/integration-test"
import {
  MESSAGE_MAX_LENGTH,
  listIntegrationMessages,
  sendIntegrationMessage,
  type IntegrationMessage,
} from "~/lib/api"

const MESSAGES_KEY = ["integration-messages"]

// Stop polling if the worker never picks the message up, rather than
// hammering the API for as long as the tab stays open.
const POLL_TIMEOUT_MS = 60_000

const COUNTER_ID = "message-character-count"

export function meta(): Route.MetaDescriptors {
  return [
    { title: "Integration test — RemitX" },
    { name: "robots", content: "noindex" },
  ]
}

function formatTime(value: string | null) {
  if (!value) return "—"
  return new Date(value).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong."
}

export default function IntegrationTest() {
  const [draft, setDraft] = useState("")
  const [listRequested, setListRequested] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  // Spread to count code points, matching Python's len() and Postgres's
  // length(). String.length counts UTF-16 units, so an emoji would read as 2
  // and the client would refuse input the server accepts.
  const trimmed = draft.trim()
  const length = [...trimmed].length
  const tooLong = length > MESSAGE_MAX_LENGTH
  const canSend = length > 0 && !tooLong

  const messages = useQuery({
    queryKey: MESSAGES_KEY,
    queryFn: listIntegrationMessages,
    enabled: listRequested,
    // Poll only while the worker still owes us something, then stop on its
    // own. No timers to clean up, and no polling once everything is settled.
    //
    // Both bail-outs matter on a page whose job is diagnosing a broken stack:
    // a stopped worker leaves a row PENDING forever, and an API that dies
    // mid-poll keeps its last payload in the cache, so a naive check would
    // retry at 1Hz indefinitely in exactly the situations we built this for.
    refetchInterval: (query) => {
      if (query.state.status === "error") return false
      const startedWaiting = query.state.data?.some(
        (message) => message.status === "PENDING"
      )
      if (!startedWaiting) return false
      const waitedFor = Date.now() - query.state.dataUpdatedAt
      return waitedFor > POLL_TIMEOUT_MS ? false : 1000
    },
  })

  const send = useMutation({
    mutationFn: sendIntegrationMessage,
    onSuccess: (created) => {
      setDraft("")
      setListRequested(true)
      // Seed the row so the PENDING state is always visible, even when the
      // worker beats the first list fetch. Invalidating alone is a no-op on
      // the very first send, because the query is still disabled at that
      // instant; it is the enable-transition that fetches.
      queryClient.setQueryData<IntegrationMessage[]>(
        MESSAGES_KEY,
        (previous) => (previous ? [created, ...previous] : undefined)
      )
      queryClient.invalidateQueries({ queryKey: MESSAGES_KEY })
      inputRef.current?.focus()
    },
  })

  const awaitingWorker = messages.data?.some((m) => m.status === "PENDING")
  const pollTimedOut =
    awaitingWorker && Date.now() - messages.dataUpdatedAt > POLL_TIMEOUT_MS

  return (
    <GridBackground>
      <div className="flex flex-1 flex-col items-center px-6 py-16">
        <main className="flex w-full max-w-3xl flex-col gap-6">
          <FadeIn>
            <Card>
              <CardHeader>
                <CardTitle>Integration test</CardTitle>
                <CardDescription>
                  Sends a message through the full stack: API → Postgres
                  (PENDING) → Redis → Celery worker → Postgres (PROCESSED).
                  Throwaway diagnostic, not a product feature.
                </CardDescription>
              </CardHeader>

              <CardContent className="flex flex-col gap-4">
                <form
                  className="flex flex-col gap-2 sm:flex-row"
                  onSubmit={(event) => {
                    event.preventDefault()
                    if (canSend) send.mutate(trimmed)
                  }}
                >
                  <Input
                    ref={inputRef}
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="Type a message to send through the queue"
                    aria-label="Message"
                    aria-invalid={tooLong || undefined}
                    aria-describedby={COUNTER_ID}
                  />
                  <div className="flex gap-2">
                    <Button type="submit" disabled={!canSend || send.isPending}>
                      <PaperPlaneTilt />
                      {send.isPending ? "Sending…" : "Send"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setListRequested(true)
                        queryClient.invalidateQueries({
                          queryKey: MESSAGES_KEY,
                        })
                      }}
                      // isLoading, not isFetching: while polling at 1Hz the
                      // latter flips every second, and disabling a focused
                      // button drops keyboard focus to the body each time.
                      disabled={messages.isLoading}
                    >
                      <ArrowClockwise />
                      List messages
                    </Button>
                  </div>
                </form>

                <p
                  id={COUNTER_ID}
                  aria-live="polite"
                  className={cn(
                    "text-xs",
                    tooLong ? "text-destructive" : "text-muted-foreground"
                  )}
                >
                  {length} / {MESSAGE_MAX_LENGTH} characters
                  {tooLong && " — too long to send"}
                </p>

                {send.isError && (
                  <Alert variant="destructive">
                    <Warning />
                    <AlertTitle>Could not send</AlertTitle>
                    <AlertDescription>
                      {errorMessage(send.error)}
                    </AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>
          </FadeIn>

          {listRequested && (
            <FadeIn>
              <Card>
                <CardHeader>
                  {/* The PENDING -> PROCESSED flip is the whole point of this
                      page, and it happens with no interaction — without a live
                      region a screen reader would never learn it occurred. */}
                  <CardTitle>Messages</CardTitle>
                  <CardDescription role="status" aria-live="polite">
                    {pollTimedOut
                      ? "Stopped waiting — messages are still pending, so the worker may be down."
                      : awaitingWorker
                        ? "Waiting for the worker to pick up pending messages…"
                        : "All messages processed. Newest first, straight from the database."}
                  </CardDescription>
                </CardHeader>

                <CardContent className="flex flex-col gap-4">
                  {messages.isError && (
                    <Alert variant="destructive">
                      <Warning />
                      <AlertTitle>Could not load messages</AlertTitle>
                      <AlertDescription>
                        {errorMessage(messages.error)}
                      </AlertDescription>
                    </Alert>
                  )}
                  {/* Rendered alongside the error, not instead of it: v5 keeps
                      the last good data, so replacing the table would blank it
                      on a single blip mid-poll. */}
                  <MessageTable
                    messages={messages.data}
                    loading={messages.isPending && !messages.isError}
                  />
                </CardContent>
              </Card>
            </FadeIn>
          )}
        </main>
      </div>
    </GridBackground>
  )
}

function MessageTable({
  messages,
  loading,
}: {
  messages: IntegrationMessage[] | undefined
  loading: boolean
}) {
  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }

  if (!messages || messages.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No messages yet. Send one above.
      </p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Message</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Processed</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {messages.map((message) => (
          <TableRow key={message.id}>
            <TableCell className="max-w-xs truncate" title={message.body}>
              {message.body}
            </TableCell>
            <TableCell>
              <Badge
                variant={
                  message.status === "PROCESSED" ? "default" : "secondary"
                }
              >
                {message.status}
              </Badge>
            </TableCell>
            <TableCell>{formatTime(message.created_at)}</TableCell>
            <TableCell>{formatTime(message.processed_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
