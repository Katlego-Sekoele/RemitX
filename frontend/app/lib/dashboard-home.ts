/** Where a signed-in user should land from marketing chrome. */

export function dashboardHomePath(isAdmin: boolean | undefined): string {
  return isAdmin ? "/admin" : "/app"
}

export function dashboardHomeLabel(isAdmin: boolean | undefined): string {
  return isAdmin ? "Open staff portal" : "Open app"
}
