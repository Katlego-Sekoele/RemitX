"""The allowlist is only as good as the sniffing underneath it."""

import pytest
from remitx_api.services.file_signatures import (
    CONTENT_TYPE_GIF,
    CONTENT_TYPE_JPEG,
    CONTENT_TYPE_PDF,
    CONTENT_TYPE_PNG,
    CONTENT_TYPE_SVG,
    CONTENT_TYPE_WEBP,
    sniff_content_type,
)

PDF = b"%PDF-1.7\n1 0 obj\n"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 "
GIF = b"GIF89a\x01\x00\x01\x00"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script></svg>'


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (PDF, CONTENT_TYPE_PDF),
        (JPEG, CONTENT_TYPE_JPEG),
        (PNG, CONTENT_TYPE_PNG),
        (WEBP, CONTENT_TYPE_WEBP),
        (GIF, CONTENT_TYPE_GIF),
    ],
)
def test_formats_are_identified_by_their_leading_bytes(body, expected):
    assert sniff_content_type(body) == expected


@pytest.mark.parametrize(
    "body",
    [
        SVG,
        b'<?xml version="1.0" encoding="UTF-8"?>\n' + SVG,
        b"\xef\xbb\xbf  \n<svg />",
        b"<!-- a comment -->\n<svg></svg>",
    ],
)
def test_svg_is_recognised_however_it_is_wrapped(body):
    """Recognised so the refusal can say *why* — an SVG carries script and
    these files are rendered back to reviewers."""
    assert sniff_content_type(body) == CONTENT_TYPE_SVG


def test_an_executable_renamed_to_pdf_is_not_a_pdf():
    """The case an extension check and a Content-Type check both miss."""
    assert sniff_content_type(b"MZ\x90\x00\x03\x00\x00\x00") is None


def test_binary_containing_the_bytes_svg_is_not_svg():
    """Only documents that open as markup are considered for the XML path."""
    assert sniff_content_type(PNG + b"<svg>") == CONTENT_TYPE_PNG


def test_unrecognised_content_is_none_rather_than_a_guess():
    assert sniff_content_type(b"") is None
    assert sniff_content_type(b"just some text") is None
