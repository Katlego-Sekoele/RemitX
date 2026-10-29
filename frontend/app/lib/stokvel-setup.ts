/**
 * The Organiser's setup wizard (people → payout order → schedule → start).
 *
 * The payout order is arranged from the invite list, not only from people who
 * have already joined, so the Organiser can place someone who is still
 * deciding. The API stores member ids (`PUT /stokvels/{id}/payout-order`),
 * so a person who hasn't accepted yet is kept in this draft and written once
 * they have a `member_id`. That draft lives in this tab's sessionStorage:
 * another tab starts from the saved member order. Starting stays closed
 * until every invite on the list has been accepted.
 */

import type { StokvelDetailRead, StokvelMemberRead } from "~/client"
import {
  formingCycleNumber,
  goingIntoCycle,
  InvitationStatus,
  pendingInvitations,
  plannedPayoutOrder,
  undecidedMembers,
} from "~/lib/stokvels"

export const SETUP_STEPS = [
  { key: "people", title: "People" },
  { key: "order", title: "Payout order" },
  { key: "schedule", title: "Schedule" },
  { key: "start", title: "Start" },
] as const

export type SetupStep = (typeof SETUP_STEPS)[number]["key"]

/** How long a drag-reorder waits before it is saved. */
export const PAYOUT_ORDER_SAVE_DELAY_MS = 600

export type RosterStatus = "organiser" | "accepted" | "pending"

export type RosterPerson = {
  /** Member id once they have joined, otherwise `invite:<invitation_id>`. */
  key: string
  memberId: string | null
  invitationId: string | null
  userId: string | null
  name: string
  isMe: boolean
  status: RosterStatus
}

export const ROSTER_STATUS_LABELS: Record<RosterStatus, string> = {
  organiser: "Organiser",
  accepted: "Accepted",
  pending: "Pending",
}

export function inviteRosterKey(invitationId: string): string {
  return `invite:${invitationId}`
}

type RosterDetail = Pick<
  StokvelDetailRead,
  "members" | "invitations" | "cycle"
> &
  Partial<Pick<StokvelDetailRead, "previous_cycle">>

/** People the cycle is being arranged for: members going in, then pending
 * invitations. Declined, revoked and lapsed invitations are left out. */
export function cycleRoster(detail: RosterDetail): RosterPerson[] {
  const accepted = detail.invitations.filter(
    (invitation) => invitation.status === InvitationStatus.accepted
  )
  const claimed = new Set<string>()
  const people: RosterPerson[] = goingIntoCycle(detail).map((member) => {
    const invitation = member.is_organiser
      ? undefined
      : accepted.find(
          (candidate) =>
            !claimed.has(candidate.invitation_id) &&
            candidate.invitee_user_id != null &&
            candidate.invitee_user_id === member.user_id
        )
    if (invitation) claimed.add(invitation.invitation_id)
    return personFromMember(member, invitation?.invitation_id ?? null)
  })

  for (const invitation of pendingInvitations(detail)) {
    people.push({
      key: inviteRosterKey(invitation.invitation_id),
      memberId: null,
      invitationId: invitation.invitation_id,
      userId: null,
      name: invitation.invitee_name ?? "Invited",
      isMe: false,
      status: "pending",
    })
  }
  return people
}

function personFromMember(
  member: StokvelMemberRead,
  invitationId: string | null
): RosterPerson {
  return {
    key: member.member_id,
    memberId: member.member_id,
    invitationId,
    userId: member.user_id,
    name: member.is_me ? "You" : (member.full_name ?? "A member"),
    isMe: member.is_me,
    status: member.is_organiser ? "organiser" : "accepted",
  }
}

/**
 * `draftKeys` is the order the Organiser last arranged, including invite
 * keys. A key whose invitation has since been accepted is swapped for that
 * member, in the same place. With no draft, the saved member order is used
 * and anyone new (including pending invitations) is added at the end.
 */
export function arrangeRoster(
  roster: readonly RosterPerson[],
  savedMemberIds: readonly string[],
  draftKeys: readonly string[] | null
): RosterPerson[] {
  const byKey = new Map(roster.map((person) => [person.key, person]))
  const byInvite = new Map(
    roster
      .filter((person) => person.invitationId)
      .map((person) => [inviteRosterKey(person.invitationId!), person])
  )
  const preferred =
    draftKeys && draftKeys.length > 0
      ? draftKeys
      : [
          ...savedMemberIds,
          ...roster
            .map((person) => person.key)
            .filter((key) => !savedMemberIds.includes(key)),
        ]

  const seen = new Set<string>()
  const ordered: RosterPerson[] = []
  for (const key of preferred) {
    const person = byKey.get(key) ?? byInvite.get(key)
    if (!person || seen.has(person.key)) continue
    seen.add(person.key)
    ordered.push(person)
  }
  for (const person of roster) {
    if (!seen.has(person.key)) ordered.push(person)
  }
  return ordered
}

/** Member ids in roster order, skipping anyone who hasn't joined. */
export function joinedMemberIds(order: readonly RosterPerson[]): string[] {
  return order.flatMap((person) => (person.memberId ? [person.memberId] : []))
}

export function sameIds(
  left: readonly string[],
  right: readonly string[]
): boolean {
  return (
    left.length === right.length &&
    left.every((id, index) => id === right[index])
  )
}

/** 1-based. Unknown keys fall back to the first step. */
export function setupStepNumber(step: string): number {
  const index = SETUP_STEPS.findIndex((item) => item.key === step)
  return index === -1 ? 1 : index + 1
}

export function setupStepByNumber(step: number): SetupStep {
  return SETUP_STEPS[step - 1]?.key ?? "people"
}

/**
 * The furthest step the stepper may open. People is always open. The order
 * and the schedule open once someone besides the Organiser is on the list.
 * Start opens only once the schedule is valid and the cycle is allowed to
 * start (everyone invited has joined, and the API's other checks pass).
 */
export function setupMaxStep(input: {
  rosterCount: number
  scheduleReady: boolean
  canStart: boolean
}): number {
  if (input.rosterCount < 2) return 1
  if (!input.scheduleReady || !input.canStart) return 3
  return 4
}

/**
 * The notice above the setup step while people are still to answer: who has
 * joined out of everyone on the invite list and, from cycle 2, the last
 * cycle's members who haven't said whether they continue. The Organiser is
 * included; declined, revoked and lapsed invitations don't count. Once
 * nobody is left to answer and there are at least 2 members, it says there
 * are enough to start (the other start checks are on the Start step).
 */
export function setupNotice(
  detail: Pick<StokvelDetailRead, "members" | "invitations"> &
    Partial<Pick<StokvelDetailRead, "previous_cycle">>
): { title: string; description: string } {
  const joined = goingIntoCycle(detail).length
  const waiting = pendingInvitations(detail).length
  const deciding = undecidedMembers(detail)
  if (waiting > 0 || deciding.length > 0) {
    const parts = [
      waiting > 0
        ? "You can start the cycle once everyone you've invited has joined."
        : null,
      deciding.length > 0
        ? `${deciding.length === 1 ? "1 member hasn't" : `${deciding.length} members haven't`} said yet whether they're joining this cycle. Anyone who hasn't by the time it starts is left out.`
        : null,
      "A cycle needs at least 2 members, you included.",
    ]
    return {
      title: `${joined} of ${joined + waiting + deciding.length} joined`,
      description: parts.filter(Boolean).join(" "),
    }
  }
  if (joined < 2) {
    return {
      title: "Only you so far",
      description:
        "Invite at least one person. A cycle needs at least 2 members, you included.",
    }
  }
  return {
    title: `${joined} of ${joined} joined`,
    description: "You have enough members to start the cycle.",
  }
}

/** Why Next on the people step is closed, or null when it is open. */
export function setupPeopleHint(
  detail: Pick<StokvelDetailRead, "members" | "cycle"> &
    Partial<Pick<StokvelDetailRead, "previous_cycle">>,
  rosterCount: number
): string | null {
  if (rosterCount >= 2) return null
  const deciding = undecidedMembers(detail)
  if (deciding.length > 0) {
    return `Waiting for ${memberNames(deciding)} to join cycle ${formingCycleNumber(detail)}.`
  }
  return "Invite at least one person."
}

/** "Petrus", "Petrus and Priya", "Petrus, Priya and Sam". Used mid-sentence,
 * so a member with no name on file is "a member". */
function memberNames(members: readonly StokvelMemberRead[]): string {
  const names = members.map((member) => member.full_name ?? "a member")
  if (names.length <= 1) return names.join("")
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`
}

export function clampSetupStep(step: string, maxStep: number): SetupStep {
  const number = setupStepNumber(step)
  return setupStepByNumber(Math.min(number, maxStep))
}

const DRAFT_PREFIX = "remitx.stokvel-order."

export function readRosterDraft(stokvelId: string): string[] | null {
  if (typeof sessionStorage === "undefined") return null
  try {
    const raw = sessionStorage.getItem(DRAFT_PREFIX + stokvelId)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (
      !Array.isArray(parsed) ||
      !parsed.every((key) => typeof key === "string")
    ) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

/** This tab only. Pending invitees have no member id, so their place is not
 * sent to the server and a new tab does not see it. */
export function writeRosterDraft(stokvelId: string, keys: readonly string[]) {
  if (typeof sessionStorage === "undefined") return
  sessionStorage.setItem(DRAFT_PREFIX + stokvelId, JSON.stringify(keys))
}

/** The saved order for a detail, used when there is no local draft. */
export function savedRosterOrder(detail: Pick<StokvelDetailRead, "cycle">) {
  return plannedPayoutOrder(detail)
}
