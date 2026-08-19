import { type RouteConfig, index, route } from "@react-router/dev/routes"

export default [
  index("routes/home.tsx"),
  route("integration-test", "routes/integration-test.tsx"),
] satisfies RouteConfig
