`get_current_user` can hit Clerk on a cold JWKS path; it is sync so only that request stalls, but first-time users also trigger Clerk API calls for email/first name during provisioning.
