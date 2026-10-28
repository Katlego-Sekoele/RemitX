from remitx_api.errors.base import DomainError, ForbiddenError, NotFoundError


class TrustMeBankDisabledError(DomainError):
    def __init__(self) -> None:
        super().__init__("TrustMeBank integration is not enabled on this environment.")


class TrustMeBankNotLinkedError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Connect your TrustMeBank account before paying through the bank."
        )


class TrustMeBankOAuthStateError(DomainError):
    def __init__(self) -> None:
        super().__init__("The bank connection request expired or was invalid.")


class TrustMeBankDepositNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("No deposit matches that TrustMeBank payment.")


class TrustMeBankKycRequiredError(ForbiddenError):
    def __init__(self) -> None:
        super().__init__(
            "Only verified customers can add money through TrustMeBank."
        )
