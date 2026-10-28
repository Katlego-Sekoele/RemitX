"""HTTP client for the TrustMeBank Open Banking API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from remitx_api.config import Config


class TrustMeBankClientError(Exception):
    pass


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str
    consent_id: str


@dataclass(frozen=True)
class PaymentResponse:
    payment_id: str
    status: str
    amount: str
    currency: str
    reference: str
    authorisation_url: str


class TrustMeBankClient:
    def __init__(self, config: Config | None = None) -> None:
        self._config = config or Config()

    @property
    def base_url(self) -> str:
        return self._config.TRUSTMEBANK_URL.rstrip("/")

    def authorize_url(self, *, state: str, redirect_uri: str, scope: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self._config.TRUSTMEBANK_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
        }
        return f"{self.base_url}/oauth/authorize?{urlencode(params)}"

    def exchange_code(
        self, *, code: str, redirect_uri: str
    ) -> TokenResponse:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._config.TRUSTMEBANK_CLIENT_ID,
            "client_secret": self._config.TRUSTMEBANK_CLIENT_SECRET,
        }
        payload = self._post_form("/oauth/token", data=data)
        return TokenResponse(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_in=int(payload["expires_in"]),
            scope=payload["scope"],
            consent_id=payload["consent_id"],
        )

    def refresh_tokens(self, *, refresh_token: str) -> TokenResponse:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._config.TRUSTMEBANK_CLIENT_ID,
            "client_secret": self._config.TRUSTMEBANK_CLIENT_SECRET,
        }
        payload = self._post_form("/oauth/token", data=data)
        return TokenResponse(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_in=int(payload["expires_in"]),
            scope=payload["scope"],
            consent_id=payload["consent_id"],
        )

    def get_me(self, *, access_token: str) -> dict[str, Any]:
        return self._get("/api/v1/me", access_token=access_token)

    def list_accounts(self, *, access_token: str) -> list[dict[str, Any]]:
        payload = self._get("/api/v1/accounts", access_token=access_token)
        return list(payload.get("data") or [])

    def create_payment(
        self,
        *,
        access_token: str,
        idempotency_key: str,
        debtor_account_id: str,
        creditor_account_number: str,
        amount: str,
        reference: str,
        redirect_uri: str,
    ) -> PaymentResponse:
        body = {
            "debtor_account_id": debtor_account_id,
            "creditor_account_number": creditor_account_number,
            "amount": amount,
            "currency": "ZAR",
            "reference": reference,
            "redirect_uri": redirect_uri,
        }
        payload = self._post_json(
            "/api/v1/payments",
            access_token=access_token,
            json=body,
            headers={"Idempotency-Key": idempotency_key},
            expected=(201, 200),
        )
        return PaymentResponse(
            payment_id=payload["payment_id"],
            status=payload["status"],
            amount=payload["amount"],
            currency=payload["currency"],
            reference=payload["reference"],
            authorisation_url=payload["authorisation_url"],
        )

    def get_payment(self, *, access_token: str, payment_id: str) -> dict[str, Any]:
        return self._get(
            f"/api/v1/payments/{payment_id}", access_token=access_token
        )

    def _get(self, path: str, *, access_token: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise TrustMeBankClientError("TrustMeBank request failed") from exc
        return self._parse_json(response)

    def _post_form(self, path: str, *, data: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.post(url, data=data, timeout=15.0)
        except httpx.HTTPError as exc:
            raise TrustMeBankClientError("TrustMeBank token request failed") from exc
        return self._parse_json(response)

    def _post_json(
        self,
        path: str,
        *,
        access_token: str,
        json: dict[str, Any],
        headers: dict[str, str] | None = None,
        expected: tuple[int, ...] = (201,),
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        merged = {"Authorization": f"Bearer {access_token}"}
        if headers:
            merged.update(headers)
        try:
            response = httpx.post(url, json=json, headers=merged, timeout=15.0)
        except httpx.HTTPError as exc:
            raise TrustMeBankClientError("TrustMeBank payment request failed") from exc
        if response.status_code not in expected:
            raise TrustMeBankClientError(
                f"TrustMeBank returned {response.status_code}"
            )
        return self._parse_json(response)

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            raise TrustMeBankClientError(
                f"TrustMeBank returned {response.status_code}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise TrustMeBankClientError("Unexpected TrustMeBank response")
        return payload
