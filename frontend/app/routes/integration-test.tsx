import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowClockwise, PaperPlaneTilt, Warning } from "@phosphor-icons/react"
import { useState } from "react"

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
import {
  MESSAGE_MAX_LENGTH,
  listIntegrationMessages,
  sendIntegrationMessage,
  type IntegrationMessage,
} from "~/lib/api"

const MESSAGES_KEY = ["integration-messages"]

export function meta() {
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
  const queryClient = useQueryClient()

  const trimmed = draft.trim()
  const tooLong = trimmed.length > MESSAGE_MAX_LENGTH
  const canSend = trimmed.length > 0 && !tooLong

  const messages = useQuery({
    queryKey: MESSAGES_KEY,
    queryFn: listIntegrationMessages,
    enabled: listRequested,
    // Poll only while the worker still owes us something, then stop on its
    // own. No timers to clean up, and no polling once everything is settled.
    refetchInterval: (query) =>
      query.state.data?.some((message) => message.status === "PENDING")
        ? 1000
        : false,
  })

  const send = useMutation({
    mutationFn: sendIntegrationMessage,
    onSuccess: () => {
      setDraft("")
      setListRequested(true)
      queryClient.invalidateQueries({ queryKey: MESSAGES_KEY })
    },
  })

  const awaitingWorker = messages.data?.some((m) => m.status === "PENDING")

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
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="Type a message to send through the queue"
                    aria-label="Message"
                    aria-invalid={tooLong || undefined}
                    disabled={send.isPending}
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
                      disabled={messages.isFetching}
                    >
                      <ArrowClockwise />
                      List messages
                    </Button>
                  </div>
                </form>

                <p
                  className={`text-xs ${
                    tooLong ? "text-destructive" : "text-muted-foreground"
                  }`}
                >
                  {trimmed.length} / {MESSAGE_MAX_LENGTH} characters
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
                  <CardTitle>Messages</CardTitle>
                  <CardDescription>
                    {awaitingWorker
                      ? "Waiting for the worker to pick up pending messages…"
                      : "Newest first, straight from the database."}
                  </CardDescription>
                </CardHeader>

                <CardContent>
                  {messages.isError ? (
                    <Alert variant="destructive">
                      <Warning />
                      <AlertTitle>Could not load messages</AlertTitle>
                      <AlertDescription>
                        {errorMessage(messages.error)}
                      </AlertDescription>
                    </Alert>
                  ) : (
                    <MessageTable
                      messages={messages.data}
                      loading={messages.isPending}
                    />
                  )}
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
    <div className="w-full overflow-x-auto">
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
              <TableCell className="max-w-xs truncate">
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
    </div>
  )
}
