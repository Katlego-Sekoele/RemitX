import type { ReactNode } from "react"

import {
  formatDate,
  formatZar,
  humanise,
} from "~/components/admin/kyc-review/format"
import { Badge } from "~/components/ui/badge"
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "~/components/ui/card"
import {
  DescriptionDetails,
  DescriptionItem,
  DescriptionList,
  DescriptionTerm,
} from "~/components/ui/description-list"
import type {
  KycApplicantApplicationRead,
  KycApplicationRead,
  KycApplicationReadPii,
} from "~/client"
import { useKycReferenceQuery } from "~/hooks/use-kyc-reference"
import { countryName } from "~/lib/kyc-reference"

/** The declared fields, masked (staff), revealed (staff) or the applicant's
 * own. These cards read nothing else, so they are shared by both portals. */
type Application =
  KycApplicationRead | KycApplicationReadPii | KycApplicantApplicationRead

function Section({
  title,
  action,
  children,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {action ? <CardAction>{action}</CardAction> : null}
      </CardHeader>
      <CardContent>
        <DescriptionList>{children}</DescriptionList>
      </CardContent>
    </Card>
  )
}

function Row({
  term,
  children,
  wide,
}: {
  term: string
  children: ReactNode
  wide?: boolean
}) {
  return (
    <DescriptionItem wide={wide}>
      <DescriptionTerm>{term}</DescriptionTerm>
      <DescriptionDetails>{children ?? "—"}</DescriptionDetails>
    </DescriptionItem>
  )
}

function YesNo({ value }: { value: boolean | null | undefined }) {
  if (value == null) return "—"
  return value ? <Badge variant="destructive">Yes</Badge> : "No"
}

export function IdentitySection({
  application,
  revealAction,
}: {
  application: Application
  revealAction?: ReactNode
}) {
  const { data: reference } = useKycReferenceQuery()

  return (
    <Section title="Identity" action={revealAction}>
      <Row term="Full name">{application.full_name}</Row>
      <Row term="Date of birth">{application.date_of_birth}</Row>
      <Row term="Nationality">
        {countryName(reference, application.nationality)}
      </Row>
      <Row term="ID type">
        <span className="capitalize">{humanise(application.id_type)}</span>
      </Row>
      <Row term="ID number">{application.id_number}</Row>
      <Row term="Issuing country">
        {countryName(reference, application.issuing_country)}
      </Row>
      <Row term="ID expiry">{formatDate(application.id_expiry_date)}</Row>
    </Section>
  )
}

export function ContactSection({ application }: { application: Application }) {
  const { data: reference } = useKycReferenceQuery()
  const address = [
    application.residential_line1,
    application.residential_line2,
    application.residential_city,
    application.residential_postal_code,
    application.residential_country
      ? countryName(reference, application.residential_country)
      : null,
  ]
    .filter(Boolean)
    .join(", ")

  return (
    <Section title="Contact and address">
      <Row term="Email">{application.email}</Row>
      <Row term="Mobile">{application.mobile_number}</Row>
      <Row term="Residential address" wide>
        {address || null}
      </Row>
    </Section>
  )
}

export function FundsSection({ application }: { application: Application }) {
  return (
    <Section title="Funds">
      <Row term="Source of funds">
        <span className="capitalize">
          {humanise(application.source_of_funds)}
        </span>
      </Row>
      <Row term="Expected monthly volume">
        {formatZar(application.expected_monthly_volume_zar)}
      </Row>
      {application.source_of_funds_detail ? (
        <Row term="Source of funds detail" wide>
          {application.source_of_funds_detail}
        </Row>
      ) : null}
      {application.source_of_wealth ? (
        <Row term="Source of wealth" wide>
          {application.source_of_wealth}
        </Row>
      ) : null}
    </Section>
  )
}

export function PepSection({ application }: { application: Application }) {
  const { data: reference } = useKycReferenceQuery()

  return (
    <Section title="PEP declaration">
      <Row term="Foreign prominent public official">
        <YesNo value={application.is_foreign_prominent_public_official} />
      </Row>
      <Row term="Domestic prominent influential person">
        <YesNo value={application.is_domestic_prominent_influential_person} />
      </Row>
      <Row term="Family member or close associate">
        <YesNo value={application.is_pep_family_or_close_associate} />
      </Row>
      {application.declares_pep ? (
        <>
          <Row term="Relationship">
            <span className="capitalize">
              {humanise(application.pep_relationship)}
            </span>
          </Row>
          <Row term="Position">{application.pep_position}</Row>
          <Row term="Country">
            {countryName(reference, application.pep_country)}
          </Row>
          {application.pep_details ? (
            <Row term="Details" wide>
              {application.pep_details}
            </Row>
          ) : null}
        </>
      ) : null}
    </Section>
  )
}
