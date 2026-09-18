import uuid
from decimal import Decimal

from remitx_api.models.orm.quote import Quote
from remitx_api.services import quote_service
from remitx_api.services.quote_service import RemittancePricing


class QuoteController:
    def create_quote(
        self,
        sender_user_id: uuid.UUID,
        beneficiary_id: uuid.UUID,
        sender_amount: Decimal,
    ) -> Quote:
        return quote_service.create_quote(sender_user_id, beneficiary_id, sender_amount)

    def preview_quote(
        self,
        sender_amount: Decimal,
        sender_currency: str,
        receiver_payout_currency: str,
    ) -> RemittancePricing:
        return quote_service.preview_quote(
            sender_amount, sender_currency, receiver_payout_currency
        )
