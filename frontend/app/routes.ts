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
      ...getFlattenedAppRoutes([
        { path: "app/profile/*", module: "routes/app/profile.tsx" },
      ]).map(({ path, module }) => route(path, module)),
      layout("routes/app/verification/layout.tsx", [
        route(
          "app/profile/verification/new",
          "routes/app/verification/new.tsx"
        ),
        route(
          "app/profile/verification/:applicationId",
          "routes/app/verification/application.tsx"
        ),
        layout("routes/app/verification/steps-layout.tsx", [
          route(
            "app/profile/verification/:applicationId/identity",
            "routes/app/verification/identity.tsx"
          ),
          route(
            "app/profile/verification/:applicationId/id-document",
            "routes/app/verification/id-document.tsx"
          ),
          route(
            "app/profile/verification/:applicationId/address",
            "routes/app/verification/address.tsx"
          ),
          route(
            "app/profile/verification/:applicationId/contact",
            "routes/app/verification/contact.tsx"
          ),
          route(
            "app/profile/verification/:applicationId/financial",
            "routes/app/verification/financial.tsx"
          ),
          route(
            "app/profile/verification/:applicationId/declarations",
            "routes/app/verification/declarations.tsx"
          ),
          route(
            "app/profile/verification/:applicationId/review",
            "routes/app/verification/review.tsx"
          ),
        ]),
      ]),
    ]),
    route("integration-test", "routes/integration-test.tsx"),
    layout(
      "routes/admin/layout.tsx",
      getFlattenedAdminRoutes().map(({ path, module }) => route(path, module))
    ),
  ]),
] satisfies RouteConfig
