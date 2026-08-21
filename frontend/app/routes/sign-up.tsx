import { SignUp } from "@clerk/react-router"

import { AuthSplitLayout } from "~/components/auth-split-layout"
import type { Route } from "./+types/sign-up"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Sign up — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function SignUpPage() {
  return (
    <AuthSplitLayout>
      <SignUp signInUrl="/sign-in" />
    </AuthSplitLayout>
  )
}
