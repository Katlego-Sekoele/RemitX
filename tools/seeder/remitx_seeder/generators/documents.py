"""SPECIMEN KYC documents: an ID card or passport page and a utility bill,
drawn with Pillow.

They exist so a reviewer can do their actual job on seeded data — does the
document match the declaration? — and they are unmistakably fake: every one
carries "SPECIMEN - TEST DATA - NOT A REAL DOCUMENT" and a diagonal watermark,
shows no photograph, and copies no real document's layout or security marks.

Every file is unique (a serial and the persona's details are drawn on it): the
API refuses a second upload of identical bytes to the same application.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from remitx_seeder.generators.personas import Persona

# Plain hyphens: Pillow's bundled font has no em dash glyph.
SPECIMEN_BANNER = "SPECIMEN - TEST DATA - NOT A REAL DOCUMENT"

COUNTRY_NAMES = {
    "ZA": "South Africa",
    "ZW": "Zimbabwe",
    "NA": "Namibia",
    "US": "United States",
}

# Content types the API accepts for KYC uploads (models/orm/kyc_document.py).
PNG = "image/png"
JPEG = "image/jpeg"
PDF = "application/pdf"


@dataclass(frozen=True)
class RenderedDocument:
    body: bytes
    content_type: str
    blurry: bool


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1 has no sized default font
        return ImageFont.load_default()


def _watermark(image: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(max(image.size) // 9)
    draw.text(
        (image.size[0] // 7, image.size[1] // 3),
        "SPECIMEN",
        font=font,
        fill=(200, 30, 30, 70),
    )
    rotated = overlay.rotate(28, expand=False)
    return Image.alpha_composite(image.convert("RGBA"), rotated).convert("RGB")


def _banner(draw: ImageDraw.ImageDraw, width: int, y: int, size: int) -> None:
    draw.rectangle([(0, y), (width, y + size + 14)], fill=(190, 25, 25))
    draw.text((16, y + 6), SPECIMEN_BANNER, font=_font(size), fill="white")


def _encode(image: Image.Image, content_type: str) -> bytes:
    buffer = io.BytesIO()
    if content_type == PNG:
        image.save(buffer, format="PNG", optimize=True)
    elif content_type == JPEG:
        image.save(buffer, format="JPEG", quality=85)
    else:
        image.save(buffer, format="PDF", resolution=110)
    return buffer.getvalue()


def identity_document(
    rng: random.Random, persona: Persona, *, blurry: bool = False
) -> RenderedDocument:
    """A card-shaped identity document naming the persona's own ID."""
    ident = persona.identification
    if ident is None:
        raise ValueError(f"{persona.key} has no identification to draw")
    width, height = 1012, 638
    image = Image.new("RGB", (width, height), (236, 242, 236))
    draw = ImageDraw.Draw(image)
    _banner(draw, width, 0, 26)
    issuer = COUNTRY_NAMES.get(ident.issuing_country, ident.issuing_country)
    kind = "Identity Card" if ident.id_type == "national_id" else "Passport"
    draw.text(
        (30, 58), f"{issuer} - {kind} (specimen)", font=_font(34), fill=(20, 60, 30)
    )
    # A silhouette box instead of a face: no photograph of anyone, ever.
    draw.rectangle(
        [(30, 120), (270, 430)], outline=(90, 90, 90), width=3, fill=(210, 214, 210)
    )
    draw.ellipse([(105, 160), (195, 250)], fill=(160, 164, 160))
    draw.rectangle([(85, 265), (215, 400)], fill=(160, 164, 160))
    rows = [
        ("Surname", persona.last_name.upper()),
        ("Names", persona.first_name.upper()),
        ("Sex", "F" if persona.female else "M"),
        ("Nationality", COUNTRY_NAMES.get(persona.nationality, persona.nationality)),
        ("Date of birth", persona.date_of_birth.strftime("%d %b %Y").upper()),
        ("Number", ident.number),
    ]
    if ident.expiry:
        rows.append(("Date of expiry", ident.expiry.strftime("%d %b %Y").upper()))
    y = 125
    for label, value in rows:
        draw.text((310, y), label, font=_font(20), fill=(90, 90, 90))
        draw.text((310, y + 22), value, font=_font(30), fill=(10, 10, 10))
        y += 62
    serial = f"SPEC-{rng.randint(10**7, 10**8 - 1)}"
    draw.text(
        (30, height - 60),
        f"Specimen serial {serial}",
        font=_font(20),
        fill=(90, 90, 90),
    )
    _banner(draw, width, height - 34, 18)
    image = _watermark(image)
    if blurry:
        image = image.filter(ImageFilter.GaussianBlur(radius=7))
    content_type = rng.choice([PNG, JPEG])
    return RenderedDocument(_encode(image, content_type), content_type, blurry)


def proof_of_address(
    rng: random.Random, persona: Persona, statement_date: date, *, blurry: bool = False
) -> RenderedDocument:
    """A municipal account statement addressed to the persona, as a PDF (or
    a phone photo of one, as a JPEG)."""
    address = persona.address
    if address is None:
        raise ValueError(f"{persona.key} has no address to draw")
    width, height = 1240, 1754
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    _banner(draw, width, 0, 30)
    draw.text(
        (60, 90),
        f"City of {address.city} (specimen)",
        font=_font(46),
        fill=(15, 50, 110),
    )
    draw.text(
        (60, 150), "Municipal account statement", font=_font(30), fill=(60, 60, 60)
    )
    account = f"{rng.randint(10**9, 10**10 - 1)}"
    lines = [
        persona.full_name.upper(),
        address.line1,
        address.line2 or "",
        f"{address.city} {address.postal_code}",
        COUNTRY_NAMES.get(address.country, address.country),
    ]
    y = 260
    for line in lines:
        if line:
            draw.text((60, y), line, font=_font(30), fill=(10, 10, 10))
            y += 44
    draw.text(
        (760, 260), f"Account number: {account}", font=_font(24), fill=(10, 10, 10)
    )
    draw.text(
        (760, 300),
        f"Statement date: {statement_date:%d %B %Y}",
        font=_font(24),
        fill=(10, 10, 10),
    )
    total = Decimal(rng.randint(35000, 185000)) / 100
    table_y = 560
    for item, share in (
        ("Water and sanitation", 0.35),
        ("Electricity", 0.45),
        ("Refuse removal", 0.2),
    ):
        draw.text((60, table_y), item, font=_font(28), fill=(30, 30, 30))
        draw.text(
            (980, table_y),
            f"R {total * Decimal(str(share)):,.2f}",
            font=_font(28),
            fill=(30, 30, 30),
        )
        table_y += 56
    draw.line([(60, table_y + 10), (1180, table_y + 10)], fill=(0, 0, 0), width=2)
    draw.text((60, table_y + 30), "Amount due", font=_font(32), fill=(0, 0, 0))
    draw.text((960, table_y + 30), f"R {total:,.2f}", font=_font(32), fill=(0, 0, 0))
    _banner(draw, width, height - 40, 24)
    image = _watermark(image)
    if blurry:
        image = image.filter(ImageFilter.GaussianBlur(radius=6))
    content_type = PDF if rng.random() < 0.7 else JPEG
    return RenderedDocument(_encode(image, content_type), content_type, blurry)
