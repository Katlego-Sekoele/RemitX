import { ShieldWarningIcon } from "@phosphor-icons/react"

import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert"

type SelfDeclaredNoticeProps = {
  /** Who is reading: a reviewer deciding on declarations, or the applicant
   * making them. The fact is the same; the wording is for the reader. */
  audience: "reviewer" | "applicant"
}

/**
 * The scope caveat every KYC screen has to state: nothing an applicant
 * declares is checked against a sanctions list, a PEP database or an
 * adverse-media source. Declarations are self-declared and reviewed by a
 * person — claiming screening that does not happen is worse than not
 * screening, so no screen showing a declaration or a risk rating leaves this
 * out.
 */
export function SelfDeclaredNotice({ audience }: SelfDeclaredNoticeProps) {
  return (
    <Alert>
      <ShieldWarningIcon />
      <AlertTitle>Self-declared, not screened</AlertTitle>
      <AlertDescription>
        {audience === "reviewer" ? (
          <>
            Every declaration here — politically exposed person status, source
            of funds, source of wealth, nationality — is the applicant&apos;s
            own, and the risk rating is computed from those declarations alone.
            None of it has been checked against any sanctions list, PEP register
            or adverse-media source.
          </>
        ) : (
          <>
            What you declare is reviewed by our compliance team. RemitX does not
            check it against any sanctions list, PEP register or adverse-media
            source, so please answer accurately — a false declaration is grounds
            to reject or close your account.
          </>
        )}
      </AlertDescription>
    </Alert>
  )
}
