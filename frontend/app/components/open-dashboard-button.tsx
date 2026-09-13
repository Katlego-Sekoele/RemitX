import { Link } from "react-router"

import { Button } from "~/components/ui/button"
import { useMePermissions } from "~/hooks/use-permissions"
import { dashboardHomeLabel, dashboardHomePath } from "~/lib/dashboard-home"

type OpenDashboardButtonProps = {
  size?: "sm" | "lg"
}

/** Sends the signed-in caller to `/app`, or `/admin` when they are staff. */
export function OpenDashboardButton({ size = "sm" }: OpenDashboardButtonProps) {
  const access = useMePermissions()
  const href = dashboardHomePath(access.data?.is_admin)
  const label = dashboardHomeLabel(access.data?.is_admin)

  return (
    <Button
      size={size}
      variant={size === "sm" ? "outline" : "default"}
      nativeButton={false}
      render={<Link to={href} />}
    >
      {label}
    </Button>
  )
}
