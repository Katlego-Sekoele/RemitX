import { ShieldWarningIcon } from "@phosphor-icons/react"

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"

type SelfDeclaredNoticeProps = {
  /** Who is reading: a reviewer deciding on declarations, or the applicant
   * making them. The fact is the same; the wording is for the reader. */
  audience: "reviewer" | "applicant"
}

/** Declarations are the applicant's own and are never screened against
 * sanctions, PEP or adverse-media lists — no screen may imply otherwise. */
export function SelfDeclaredNotice({ audience }: SelfDeclaredNoticeProps) {
  return (
    <Alert>
      <ShieldWarningIcon />
      <AlertTitle>Self-declared</AlertTitle>
      <AlertDescription>
        {audience === "reviewer"
          ? "Declarations haven't been screened against sanctions or PEP lists."
          : "Answer accurately. A false declaration can get your application rejected."}
      </AlertDescription>
    </Alert>
  )
}
