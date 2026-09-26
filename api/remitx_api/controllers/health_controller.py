from remitx_api.config import Config


class HealthController:
    def get_status(self) -> dict[str, str]:
        return {
            "status": "ok",
            "settlement_token_currency": Config().UCTUSD_TOKEN_NAME,
        }
