/** Clerk image optimization query params (see Clerk image optimization guide). */
export function clerkProfileImageUrl(
  imageUrl: string,
  size: number = 80
): string {
  const params = new URLSearchParams({
    width: String(size),
    height: String(size),
    fit: "crop",
  })
  const separator = imageUrl.includes("?") ? "&" : "?"
  return `${imageUrl}${separator}${params}`
}
