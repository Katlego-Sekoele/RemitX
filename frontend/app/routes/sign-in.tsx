import { SignIn } from "@clerk/react-router"

import { AuthSplitLayout } from "~/components/auth-split-layout"
import type { Route } from "./+types/sign-in"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Sign in — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function SignInPage() {
  return (
    <AuthSplitLayout>
      <SignIn signUpUrl="/sign-up" />
    </AuthSplitLayout>
  )
}
