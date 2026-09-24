import { Avatar, AvatarFallback, AvatarImage } from "~/components/ui/avatar"
import {
  type BeneficiaryNameSource,
  beneficiaryInitials,
  beneficiaryName,
} from "~/lib/beneficiaries"
import { clerkProfileImageUrl } from "~/lib/clerk-profile-image"

type BeneficiaryLike = BeneficiaryNameSource & {
  profile_image_url?: string | null
}

export function BeneficiaryAvatar({
  beneficiary,
  size,
}: {
  beneficiary: BeneficiaryLike
  size?: "default" | "sm" | "lg"
}) {
  const name = beneficiaryName(beneficiary)
  const px = size === "sm" ? 24 : size === "lg" ? 40 : 32
  const src = beneficiary.profile_image_url
    ? clerkProfileImageUrl(beneficiary.profile_image_url, px)
    : undefined

  return (
    <Avatar size={size}>
      {src ? <AvatarImage src={src} alt={name} /> : null}
      <AvatarFallback>{beneficiaryInitials(beneficiary)}</AvatarFallback>
    </Avatar>
  )
}
