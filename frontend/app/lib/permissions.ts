/** The permission codes the admin UI branches on.
 *
 * Mirrors `PermissionCode` in api/remitx_api/models/orm/permission.py, which
 * is the authority: every one of these is enforced per route by
 * `RequirePermission` (api/remitx_api/auth/permissions.py). Hiding a page or
 * a button the caller cannot use is courtesy — never the gate.
 */
export const PERMISSIONS = {
  cashinRead: "cashin:read",
  cashinConfirm: "cashin:confirm",
  kycApplicationRead: "kyc:application:read",
  kycApplicationReadPii: "kyc:application:read_pii",
  kycApplicationDecide: "kyc:application:decide",
  kycApplicationRequestInfo: "kyc:application:request_info",
  kycRiskWrite: "kyc:risk:write",
  roleRead: "role:read",
  roleGrant: "role:grant",
  roleRevoke: "role:revoke",
  userRead: "user:read",
  kycDocumentRead: "kyc:document:read",
  platformAccountRead: "platform_account:read",
} as const

export type PermissionCode = (typeof PERMISSIONS)[keyof typeof PERMISSIONS]
