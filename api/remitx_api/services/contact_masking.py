"""Masking for contact details shown to someone other than their owner.

A sender's beneficiary list shows enough of a beneficiary's email and mobile
to recognise them (``t•••@gmail.com``, ``+2637••••••23``) and never the full
values: account references are guessable, so anyone could add a stranger as a
beneficiary, and the list must not become a way to read their contact details.
"""

MASK = "•"


def mask_email(email: str | None) -> str | None:
    """Keep the first character of the local part and the whole domain."""
    if not email:
        return None
    local, at, domain = email.strip().partition("@")
    if not at or not local or not domain:
        return MASK * 3
    return f"{local[0]}{MASK * 3}@{domain}"


def mask_mobile(mobile: str | None) -> str | None:
    """Keep the country code and first digit, and the last two digits, of an
    E.164 number; a number too short for that keeps only its last two."""
    if not mobile:
        return None
    value = mobile.strip()
    head = 5 if len(value) >= 9 else 0
    tail = 2 if len(value) > 2 else 0
    hidden = len(value) - head - tail
    return f"{value[:head]}{MASK * hidden}{value[len(value) - tail :]}"
