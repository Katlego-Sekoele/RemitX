import {
  type RouteConfig,
  index,
  layout,
  route,
} from "@react-router/dev/routes"

export default [
  index("routes/home.tsx"),
  // Splat paths: Clerk's components use sub-paths for multi-step flows
  // (email verification, MFA, SSO callback).
  route("sign-in/*", "routes/sign-in.tsx"),
  route("sign-up/*", "routes/sign-up.tsx"),
  layout("routes/protected.tsx", [
    route("integration-test", "routes/integration-test.tsx"),
  ]),
] satisfies RouteConfig
