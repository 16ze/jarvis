import base64

from chat_attachments import (
    MAX_IMAGE_BYTES,
    normalize_image_attachment,
)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def test_valid_jpeg_passes():
    payload = {"mime_type": "image/jpeg", "data": _b64(b"\xff\xd8\xff\xe0hello")}
    out = normalize_image_attachment(payload)
    assert out == {"mime_type": "image/jpeg", "data": payload["data"]}


def test_mimetype_camelcase_alias_accepted():
    data = _b64(b"abc")
    out = normalize_image_attachment({"mimeType": "image/png", "data": data})
    assert out == {"mime_type": "image/png", "data": data}


def test_data_url_prefix_is_stripped():
    data = _b64(b"webpbytes")
    out = normalize_image_attachment(
        {"mime_type": "image/webp", "data": f"data:image/webp;base64,{data}"}
    )
    assert out == {"mime_type": "image/webp", "data": data}


def test_rejects_non_dict():
    assert normalize_image_attachment(None) is None
    assert normalize_image_attachment("x") is None
    assert normalize_image_attachment(123) is None


def test_rejects_disallowed_mime():
    assert normalize_image_attachment({"mime_type": "application/pdf", "data": _b64(b"x")}) is None
    assert normalize_image_attachment({"mime_type": "text/plain", "data": _b64(b"x")}) is None


def test_rejects_missing_fields():
    assert normalize_image_attachment({"mime_type": "image/png"}) is None
    assert normalize_image_attachment({"data": _b64(b"x")}) is None


def test_rejects_non_base64():
    assert normalize_image_attachment({"mime_type": "image/png", "data": "not base64!!!"}) is None


def test_rejects_empty_data():
    assert normalize_image_attachment({"mime_type": "image/png", "data": ""}) is None
    assert normalize_image_attachment({"mime_type": "image/png", "data": "   "}) is None


def test_rejects_oversized():
    big = _b64(b"\x00" * (MAX_IMAGE_BYTES + 1))
    assert normalize_image_attachment({"mime_type": "image/jpeg", "data": big}) is None


def test_mime_is_case_insensitive_and_trimmed():
    data = _b64(b"gif")
    out = normalize_image_attachment({"mime_type": "  IMAGE/GIF ", "data": data})
    assert out == {"mime_type": "image/gif", "data": data}
