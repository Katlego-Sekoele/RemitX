import { SignIn } from "@clerk/react-router"

import { GridBackground } from "~/components/aceternity/grid-background"
import type { Route } from "./+types/sign-in"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Sign in — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function SignInPage() {
  return (
    <GridBackground>
      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <SignIn signUpUrl="/sign-up" />
      </div>
    </GridBackground>
  )
}
