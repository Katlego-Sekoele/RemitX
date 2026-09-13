import {
  CaretDownIcon,
  ProhibitIcon,
  ShieldWarningIcon,
  UserPlusIcon,
  WarningIcon,
} from "@phosphor-icons/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { AdminPageFrame } from "~/components/admin/admin-page-frame"
import { ForbiddenPage } from "~/components/admin/forbidden-page"
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"
import { Badge } from "~/components/ui/badge"
import { Button } from "~/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "~/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "~/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu"
import { Input } from "~/components/ui/input"
import { Skeleton } from "~/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table"
import { useHasPermission } from "~/hooks/use-permissions"
import {
  api,
  type AdminMemberRead as AdminMember,
  type RoleRead as Role,
  type ToxicCombinationRead as ToxicCombination,
  type UserSearchRead as UserSearchResult,
} from "~/client"
import { PERMISSIONS } from "~/lib/permissions"
import { adminRouteContext } from "~/routes/admin/admin.routes"
import type { Route } from "./+types/access"

// The literal path, not `import.meta.filename`: this module is bundled for
// the browser, where `import.meta` carries only `url`, so the lookup has to
// be given the key `admin.routes.ts` registers this page under.
const ROUTE_MODULE = "routes/admin/access.tsx"
const pageRoutingContext = adminRouteContext(ROUTE_MODULE)

export function meta(): Route.MetaDescriptors {
  return [
    { title: `${pageRoutingContext?.title} — RemitX` },
    { name: "robots", content: "noindex" },
  ]
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong."
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

function describePerson(person: {
  email: string | null
  base_reference: string
}) {
  return person.email ?? person.base_reference
}

/**
 * Warnings this grant would leave in place: the toxic pairs fully covered
 * once the role's permissions are added to the ones the person already has.
 *
 * The pairs come from `/admin/roles/toxic-combinations`, which reads the
 * same rows the server checks the grant against — so a rule changed in the
 * database changes this warning too, with nothing rebuilt.
 */
function warningsForGrant(
  held: readonly string[],
  role: Role | undefined,
  combinations: readonly ToxicCombination[]
): ToxicCombination[] {
  if (!role) return []
  const resulting = new Set([...held, ...role.permissions])
  return combinations.filter((combination) =>
    combination.permissions.every((permission) => resulting.has(permission))
  )
}

/**
 * Mirrors how the API gates role administration
 * (api/remitx_api/routes/admin/user_roles.py): reading who holds what needs
 * `role:read`, and the two ways to change it need `role:grant` / `role:revoke`
 * on top. The server decides; this only keeps the UI from offering what it
 * would refuse.
 */
export default function Access() {
  const canRead = useHasPermission(PERMISSIONS.roleRead)

  if (!canRead) return <ForbiddenPage />

  return <AccessPage />
}

function AccessPage() {
  const queryClient = useQueryClient()
  const canGrant = useHasPermission(PERMISSIONS.roleGrant)
  const canSearch = useHasPermission(PERMISSIONS.userRead)

  const admins = useQuery(api.admin.users.listAdmins())
  const roles = useQuery(api.admin.roles.listRoles())
  const toxicCombinations = useQuery(api.admin.roles.listToxicCombinations())

  const refreshAdmins = () =>
    queryClient.invalidateQueries({
      queryKey: api.admin.users.listAdmins().queryKey,
    })

  return (
    <AdminPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <h1 className="font-heading text-2xl font-semibold tracking-tight">
            {pageRoutingContext?.title}
          </h1>
        </div>
        {canGrant && (
          <GrantDialog
            roles={roles.data ?? []}
            combinations={toxicCombinations.data ?? []}
            canSearch={canSearch}
            onGranted={refreshAdmins}
          />
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Admins</CardTitle>
        </CardHeader>
        <CardContent>
          <AdminTable
            admins={admins.data}
            loading={admins.isPending}
            error={admins.isError ? admins.error : null}
            onChanged={refreshAdmins}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Role reference</CardTitle>
        </CardHeader>
        <CardContent>
          <RoleReference roles={roles.data} loading={roles.isPending} />
        </CardContent>
      </Card>
    </AdminPageFrame>
  )
}

function AdminTable({
  admins,
  loading,
  error,
  onChanged,
}: {
  admins: AdminMember[] | undefined
  loading: boolean
  error: unknown
  onChanged: () => void
}) {
  if (loading) return <Skeleton className="h-24 w-full" />

  if (error) {
    return (
      <Alert variant="destructive">
        <WarningIcon />
        <AlertTitle>Could not load the admin list</AlertTitle>
        <AlertDescription>{errorMessage(error)}</AlertDescription>
      </Alert>
    )
  }

  if (!admins || admins.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nobody holds an operational role yet.
      </p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Person</TableHead>
          <TableHead>Roles</TableHead>
          <TableHead>Last grant</TableHead>
          <TableHead className="w-8" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {admins.map((member) => (
          <TableRow key={member.user_id}>
            <TableCell>
              <div className="flex flex-col">
                <span>{describePerson(member)}</span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  {member.base_reference}
                </span>
              </div>
            </TableCell>
            <TableCell>
              <div className="flex flex-wrap gap-1.5">
                {member.roles.map((role) => (
                  <Badge
                    key={role.role}
                    variant={role.self_granted ? "destructive" : "secondary"}
                  >
                    {role.self_granted && <ShieldWarningIcon />}
                    {role.display_name}
                  </Badge>
                ))}
              </div>
            </TableCell>
            <TableCell>{formatDate(member.last_granted_at)}</TableCell>
            <TableCell>
              <AccessDialog member={member} onChanged={onChanged} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** One person's full grant history, and the place a role is taken back. */
function AccessDialog({
  member,
  onChanged,
}: {
  member: AdminMember
  onChanged: () => void
}) {
  const [open, setOpen] = useState(false)
  const canRevoke = useHasPermission(PERMISSIONS.roleRevoke)

  const access = useQuery({
    ...api.admin.users.getUserAccess({ path: { user_id: member.user_id } }),
    enabled: open,
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="ghost" size="sm" />}>
        Manage
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{describePerson(member)}</DialogTitle>
          <DialogDescription>Grant history, newest first.</DialogDescription>
        </DialogHeader>

        {access.isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : access.isError ? (
          <Alert variant="destructive">
            <WarningIcon />
            <AlertTitle>Could not load this account</AlertTitle>
            <AlertDescription>{errorMessage(access.error)}</AlertDescription>
          </Alert>
        ) : (
          <div className="flex flex-col gap-4">
            {access.data?.roles.map((grant) => (
              <div
                key={grant.user_role_id}
                className="flex flex-col gap-2 rounded-md border border-border p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex flex-wrap items-center gap-1.5">
                    <Badge variant={grant.active ? "default" : "outline"}>
                      {grant.display_name}
                    </Badge>
                    {grant.self_granted && (
                      <Badge variant="destructive">
                        <ShieldWarningIcon />
                        Self-granted
                      </Badge>
                    )}
                    {grant.toxic_combination_acknowledged && (
                      <Badge variant="outline">
                        <WarningIcon />
                        Warning accepted
                      </Badge>
                    )}
                    {!grant.active && (
                      <Badge variant="ghost">
                        <ProhibitIcon />
                        Revoked {formatDate(grant.revoked_at!)}
                      </Badge>
                    )}
                  </span>
                  {grant.active && canRevoke && (
                    <RevokeDialog
                      userId={member.user_id}
                      role={grant.role}
                      displayName={grant.display_name}
                      onRevoked={() => {
                        access.refetch()
                        onChanged()
                      }}
                    />
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Granted {formatDate(grant.granted_at)} —{" "}
                  {grant.grant_reason ?? "no reason recorded"}
                </p>
                {!grant.active && grant.revoke_reason && (
                  <p className="text-xs text-muted-foreground">
                    Revoked — {grant.revoke_reason}
                  </p>
                )}
              </div>
            ))}

            <div className="flex flex-col gap-2">
              <h3 className="text-xs font-medium">Effective permissions</h3>
              <div className="flex flex-wrap gap-1.5">
                {access.data?.permissions.length === 0 ? (
                  <span className="text-xs text-muted-foreground">
                    None — every active role has been revoked.
                  </span>
                ) : (
                  access.data?.permissions.map((permission) => (
                    <Badge
                      key={permission}
                      variant="secondary"
                      className="font-mono text-[11px]"
                    >
                      {permission}
                    </Badge>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function RevokeDialog({
  userId,
  role,
  displayName,
  onRevoked,
}: {
  userId: string
  role: string
  displayName: string
  onRevoked: () => void
}) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState("")

  const revoke = useMutation({
    ...api.admin.users.revokeUserRole(),
    onSuccess: () => {
      onRevoked()
      setOpen(false)
    },
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setReason("")
          revoke.reset()
        }
      }}
    >
      <DialogTrigger render={<Button variant="ghost" size="sm" />}>
        Revoke
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Revoke {displayName}</DialogTitle>
          <DialogDescription>Takes effect immediately.</DialogDescription>
        </DialogHeader>

        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (reason.trim())
              revoke.mutate({
                path: { user_id: userId, role },
                body: { reason: reason.trim() },
              })
          }}
        >
          <ReasonField
            value={reason}
            onChange={setReason}
            disabled={revoke.isPending}
            placeholder="Why this role is being taken away"
          />

          {revoke.isError && (
            <Alert variant="destructive">
              <WarningIcon />
              <AlertTitle>Could not revoke</AlertTitle>
              <AlertDescription>{errorMessage(revoke.error)}</AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button
              type="submit"
              variant="destructive"
              disabled={!reason.trim() || revoke.isPending}
            >
              {revoke.isPending ? "Revoking…" : "Revoke role"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function GrantDialog({
  roles,
  combinations,
  canSearch,
  onGranted,
}: {
  roles: Role[]
  combinations: ToxicCombination[]
  canSearch: boolean
  onGranted: () => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const [selected, setSelected] = useState<UserSearchResult | null>(null)
  const [roleName, setRoleName] = useState("")
  const [reason, setReason] = useState("")
  const [acknowledged, setAcknowledged] = useState(false)

  const results = useQuery({
    ...api.admin.users.searchUsers({ query: { email: search.trim() } }),
    enabled: canSearch && open && search.trim().length >= 3 && !selected,
  })

  const access = useQuery({
    ...api.admin.users.getUserAccess({
      path: { user_id: selected?.user_id ?? "" },
    }),
    enabled: selected != null,
  })

  const grantable = roles.filter((item) => item.is_grantable)
  const role = grantable.find((item) => item.name === roleName)
  const warnings = warningsForGrant(
    access.data?.permissions ?? [],
    role,
    combinations
  )

  const grant = useMutation({
    ...api.admin.users.grantUserRole(),
    onSuccess: () => {
      onGranted()
      setOpen(false)
    },
  })

  function reset() {
    setSearch("")
    setSelected(null)
    setRoleName("")
    setReason("")
    setAcknowledged(false)
    grant.reset()
  }

  const blockedOnWarning = warnings.length > 0 && !acknowledged
  const canSubmit =
    selected != null &&
    roleName !== "" &&
    reason.trim() !== "" &&
    !blockedOnWarning &&
    !grant.isPending

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) reset()
      }}
    >
      <DialogTrigger render={<Button />}>
        <UserPlusIcon />
        Grant a role
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Grant a role</DialogTitle>
        </DialogHeader>

        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (canSubmit && selected) {
              grant.mutate({
                path: { user_id: selected.user_id },
                body: {
                  role: roleName,
                  reason: reason.trim(),
                  toxic_combination_acknowledged: acknowledged,
                },
              })
            }
          }}
        >
          <div className="flex flex-col gap-2">
            <label className="text-xs font-medium" htmlFor="admin-search">
              Person
            </label>
            {selected ? (
              <div className="flex items-center justify-between gap-2 rounded-md border border-input px-2.5 py-1.5 text-xs">
                <span className="truncate">{describePerson(selected)}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setSelected(null)
                    setAcknowledged(false)
                  }}
                >
                  Change
                </Button>
              </div>
            ) : canSearch ? (
              <>
                <Input
                  id="admin-search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by email"
                  autoComplete="off"
                />
                {search.trim().length >= 3 && (
                  <div className="flex flex-col gap-1">
                    {results.isPending ? (
                      <Skeleton className="h-8 w-full" />
                    ) : results.data?.length === 0 ? (
                      <span className="text-xs text-muted-foreground">
                        No account matches that address.
                      </span>
                    ) : (
                      results.data?.map((person) => (
                        <Button
                          key={person.user_id}
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="justify-start"
                          onClick={() => setSelected(person)}
                        >
                          {describePerson(person)}
                        </Button>
                      ))
                    )}
                  </div>
                )}
              </>
            ) : (
              <p className="text-xs text-muted-foreground">
                Searching accounts needs the {PERMISSIONS.userRead} permission.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium">Role</span>
            <RolePicker
              roles={grantable}
              value={roleName}
              onChange={(next) => {
                setRoleName(next)
                setAcknowledged(false)
              }}
            />
            {role && (
              <div className="flex flex-col gap-1.5 rounded-md border border-border p-2.5">
                <p className="text-xs text-muted-foreground">
                  {role.description}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {role.permissions.length === 0 ? (
                    <span className="text-xs text-muted-foreground">
                      No permissions.
                    </span>
                  ) : (
                    role.permissions.map((permission) => (
                      <Badge
                        key={permission}
                        variant="secondary"
                        className="font-mono text-[11px]"
                      >
                        {permission}
                      </Badge>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          <ReasonField
            value={reason}
            onChange={setReason}
            disabled={grant.isPending}
            placeholder="Why this person needs this role"
          />

          {warnings.length > 0 && (
            <Alert variant="destructive">
              <WarningIcon />
              <AlertTitle>
                This leaves one person holding both halves of a control
              </AlertTitle>
              <AlertDescription>
                <ul className="flex list-disc flex-col gap-1 pl-4">
                  {warnings.map((warning) => (
                    <li key={warning.permissions.join("+")}>
                      <span className="font-mono text-[11px]">
                        {warning.permissions.join(" + ")}
                      </span>{" "}
                      — {warning.explanation}
                    </li>
                  ))}
                </ul>
                {!acknowledged && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-2"
                    onClick={() => setAcknowledged(true)}
                  >
                    I understand — grant it anyway
                  </Button>
                )}
              </AlertDescription>
            </Alert>
          )}

          {grant.isError && (
            <Alert variant="destructive">
              <WarningIcon />
              <AlertTitle>Could not grant that role</AlertTitle>
              <AlertDescription>{errorMessage(grant.error)}</AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button type="submit" disabled={!canSubmit}>
              {grant.isPending ? "Granting…" : "Grant role"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Role list with each role's permissions inline, so the granter sees what
 * they are actually handing over before they hand it over. */
function RolePicker({
  roles,
  value,
  onChange,
}: {
  roles: Role[]
  value: string
  onChange: (next: string) => void
}) {
  const selected = roles.find((role) => role.name === value)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="outline" className="justify-between" />}
      >
        {selected?.display_name ?? "Select a role"}
        <CaretDownIcon data-icon="inline-end" />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="max-h-80 w-[min(28rem,90vw)] overflow-y-auto">
        <DropdownMenuRadioGroup
          value={value}
          onValueChange={(next) => onChange(String(next))}
        >
          {roles.map((role) => (
            <DropdownMenuRadioItem key={role.name} value={role.name}>
              <span className="flex flex-col gap-1 py-0.5">
                <span className="font-medium">{role.display_name}</span>
                <span className="text-[11px] text-muted-foreground">
                  {role.permissions.length === 0
                    ? "No permissions"
                    : role.permissions.join(", ")}
                </span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** The reason recorded against a grant or revoke.
 *
 * Only emptiness is checked here. How long a reason has to be is the server's
 * rule (models/schemas/role.py), and its 422 says so — a copy of the number
 * in this file would be one more thing to keep in step.
 */
function ReasonField({
  value,
  onChange,
  disabled,
  placeholder,
}: {
  value: string
  onChange: (next: string) => void
  disabled: boolean
  placeholder: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-medium" htmlFor="reason">
        Reason
      </label>
      <Input
        id="reason"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
      />
      <p className="text-[11px] text-muted-foreground">Required.</p>
    </div>
  )
}

function RoleReference({
  roles,
  loading,
}: {
  roles: Role[] | undefined
  loading: boolean
}) {
  if (loading) return <Skeleton className="h-24 w-full" />

  if (!roles || roles.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        The role catalogue is empty.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Role</TableHead>
            <TableHead>What it is for</TableHead>
            <TableHead>Permissions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {roles.map((role) => (
            <TableRow key={role.role_id}>
              <TableCell className="align-top">{role.display_name}</TableCell>
              <TableCell className="max-w-xs align-top text-muted-foreground">
                {role.description}
              </TableCell>
              <TableCell className="align-top">
                <div className="flex flex-wrap gap-1.5">
                  {role.permissions.length === 0 ? (
                    <span className="text-xs text-muted-foreground">—</span>
                  ) : (
                    role.permissions.map((permission) => (
                      <Badge
                        key={permission}
                        variant="secondary"
                        className="font-mono text-[11px]"
                      >
                        {permission}
                      </Badge>
                    ))
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
