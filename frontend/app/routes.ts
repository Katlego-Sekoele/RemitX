import {
  type RouteConfig,
  index,
  layout,
  route,
} from "@react-router/dev/routes"

import { getFlattenedAdminRoutes } from "./routes/admin/admin.routes"
import { getFlattenedAppRoutes } from "./routes/app/app.routes"

export default [
  index("routes/home.tsx"),
  // Splat paths: Clerk's components use sub-paths for multi-step flows
  // (email verification, MFA, SSO callback).
  route("sign-in/*", "routes/sign-in.tsx"),
  route("sign-up/*", "routes/sign-up.tsx"),
  layout("routes/protected.tsx", [
    layout("routes/app/layout.tsx", [
      ...getFlattenedAppRoutes().map(({ path, module }) => route(path, module)),
      layout("routes/onboarding/layout.tsx", [
        route("app/verification", "routes/onboarding/welcome.tsx"),
        route("app/verification/identity", "routes/onboarding/identity.tsx"),
        route(
          "app/verification/id-document",
          "routes/onboarding/id-document.tsx"
        ),
        route("app/verification/address", "routes/onboarding/address.tsx"),
        route("app/verification/contact", "routes/onboarding/contact.tsx"),
        route("app/verification/financial", "routes/onboarding/financial.tsx"),
        route(
          "app/verification/declarations",
          "routes/onboarding/declarations.tsx"
        ),
        route("app/verification/review", "routes/onboarding/review.tsx"),
        route("app/verification/status", "routes/onboarding/status.tsx"),
      ]),
    ]),
    route("onboarding", "routes/onboarding/legacy-redirect.tsx"),
    route("onboarding/*", "routes/onboarding/legacy-redirect-splat.tsx"),
    route("integration-test", "routes/integration-test.tsx"),
    layout(
      "routes/admin/layout.tsx",
      getFlattenedAdminRoutes().map(({ path, module }) => route(path, module))
    ),
  ]),
] satisfies RouteConfig
