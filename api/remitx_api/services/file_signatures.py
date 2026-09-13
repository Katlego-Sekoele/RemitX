"""Identify an uploaded file by what is in it, not by what it claims to be.

A declared ``Content-Type`` is a client assertion and a file extension is a
naming convention; neither is evidence. ``evil.pdf.exe`` passes an extension
check and a mislabelled header passes a header check, so the only allowlist
worth having is one applied to the leading bytes of the object actually in the
bucket.

SVG gets a signature here despite never being accepted, so that the refusal can
say *why*. An SVG is a scriptable document — it carries ``<script>`` and event
handlers — and these files are rendered back to reviewers. "Unsupported file
type" is a worse answer to that upload than naming it.
"""

from __future__ import annotations

# 512 bytes covers every signature below with room for the XML prologue,
# encoding declaration and a comment that can precede an <svg> root element.
SNIFF_LENGTH = 512

CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_JPEG = "image/jpeg"
CONTENT_TYPE_PNG = "image/png"
CONTENT_TYPE_WEBP = "image/webp"
CONTENT_TYPE_GIF = "image/gif"
CONTENT_TYPE_SVG = "image/svg+xml"

# (offset, magic bytes, content type). Ordered longest-and-most-specific first
# so a prefix shared by two formats cannot resolve to the looser one.
_SIGNATURES: tuple[tuple[int, bytes, str], ...] = (
    (0, b"\x89PNG\r\n\x1a\n", CONTENT_TYPE_PNG),
    (0, b"%PDF-", CONTENT_TYPE_PDF),
    (0, b"\xff\xd8\xff", CONTENT_TYPE_JPEG),
    (0, b"GIF87a", CONTENT_TYPE_GIF),
    (0, b"GIF89a", CONTENT_TYPE_GIF),
)

_XML_LEADING = b" \t\r\n\x0b\x0c\xef\xbb\xbf"


def sniff_content_type(prefix: bytes) -> str | None:
    """The content type of a file starting with ``prefix``, or ``None``.

    ``None`` means unrecognised, which for this allowlist means rejected — an
    upload the platform cannot identify is not one it should render to a
    reviewer.
    """
    for offset, magic, content_type in _SIGNATURES:
        if prefix[offset : offset + len(magic)] == magic:
            return content_type

    # RIFF....WEBP — the four size bytes in between are not part of the match.
    if prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
        return CONTENT_TYPE_WEBP

    if _looks_like_svg(prefix):
        return CONTENT_TYPE_SVG

    return None


def _looks_like_svg(prefix: bytes) -> bool:
    """SVG has no magic number: it is XML, so it is recognised by its root.

    Checked only for documents that actually open as markup, so a binary
    format that happens to contain the bytes ``<svg`` somewhere is not
    mistaken for one.
    """
    stripped = prefix.lstrip(_XML_LEADING)
    if not stripped.startswith(b"<"):
        return False
    return b"<svg" in stripped[:SNIFF_LENGTH].lower()
