import { SignUp } from "@clerk/react-router"

import { GridBackground } from "~/components/aceternity/grid-background"
import type { Route } from "./+types/sign-up"

export function meta(): Route.MetaDescriptors {
  return [{ title: "Sign up — RemitX" }, { name: "robots", content: "noindex" }]
}

export default function SignUpPage() {
  return (
    <GridBackground>
      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <SignUp signInUrl="/sign-in" />
      </div>
    </GridBackground>
  )
}
