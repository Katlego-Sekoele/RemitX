import { redirect } from "react-router"

function destination(request: Request): string {
  const url = new URL(request.url)
  const rest = url.pathname.replace(/^\/onboarding\/?/, "")
  const path = rest ? `/app/verification/${rest}` : "/app/verification"
  return `${path}${url.search}`
}

export async function clientLoader({ request }: { request: Request }) {
  throw redirect(destination(request))
}

export default function LegacyOnboardingRedirect() {
  return null
}
