import { UserProfile } from "@clerk/react-router"
import { IdentificationBadgeIcon, PhoneIcon } from "@phosphor-icons/react"
import { useQuery, type UseQueryResult } from "@tanstack/react-query"
import type { ReactNode } from "react"

import { AppPageFrame } from "~/components/app-dashboard/app-page-frame"
import { ContactPage } from "~/components/profile/contact-page"
import { VerificationPage } from "~/components/profile/verification-page"
import { Alert, AlertDescription } from "~/components/ui/alert"
import { PageHeader, PageHeaderTitle } from "~/components/ui/page-header"
import { Skeleton } from "~/components/ui/skeleton"
import { errorMessage } from "~/hooks/use-onboarding"
import type { Route } from "./+types/profile"
import { api, type ProfileRead } from "~/client"

const ROUTE_MODULE = "routes/app/profile.tsx"

// Colours and type come from the shadcn theme set on ClerkProvider. These strip
// Clerk's card chrome so the component sits flat in the page frame like the
// rest of the dashboard. ClerkProvider's cssLayerName puts Clerk's own styles
// below Tailwind's utilities (see app.css); the `!` is for the shadcn theme's
// `shadow-sm border`, which are utilities too and would otherwise win.
// Clerk's surfaces take the page background, so anything not stripped here
// still blends in.
//
// Clerk's navbar is hidden: the app sidebar lists the same pages
// (PROFILE_SECTIONS) and drives this component by path.
const APPEARANCE = {
  variables: { colorBackground: "var(--background)" },
  elements: {
    rootBox: "w-full",
    cardBox:
      "w-full max-w-none rounded-none! border-0! bg-transparent! shadow-none!",
    navbar: "hidden",
    navbarMobileMenuRow: "hidden",
    scrollBox: "rounded-none! border-0! bg-transparent! shadow-none!",
    profilePageContent: "px-0 pt-0",
  },
}

export function meta(): Route.MetaDescriptors {
  return [{ title: "Profile — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function ProfilePage() {
  const profile = useQuery(api.me.getMyProfile())

  return (
    <AppPageFrame module={ROUTE_MODULE}>
      <div className="flex flex-col gap-6">
        <PageHeader>
          <PageHeaderTitle>Profile</PageHeaderTitle>
        </PageHeader>
        {/* Path routing, so the sidebar's links select the page. Labels and
            icons are still required by Clerk but not shown. */}
        <UserProfile routing="path" path="/app/profile" appearance={APPEARANCE}>
          <UserProfile.Page label="account" />
          <UserProfile.Page
            label="Contact"
            url="contact"
            labelIcon={<PhoneIcon />}
          >
            <Loaded query={profile}>
              {(data) => <ContactPage profile={data} />}
            </Loaded>
          </UserProfile.Page>
          <UserProfile.Page
            label="Verification"
            url="verification"
            labelIcon={<IdentificationBadgeIcon />}
          >
            <Loaded query={profile}>
              {(data) => <VerificationPage kyc={data.kyc} />}
            </Loaded>
          </UserProfile.Page>
          <UserProfile.Page label="security" />
        </UserProfile>
      </div>
    </AppPageFrame>
  )
}

function Loaded({
  query,
  children,
}: {
  query: UseQueryResult<ProfileRead, unknown>
  children: (data: ProfileRead) => ReactNode
}) {
  if (query.isPending) return <Skeleton className="h-40 w-full" />
  if (query.isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(query.error)}</AlertDescription>
      </Alert>
    )
  }
  return children(query.data)
}
