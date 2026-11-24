import asyncio
import json

from app.core.compression import (
    TEXT_PREFIX,
    decode_bytes,
    decode_json,
    decode_text,
    encode_bytes,
    encode_json,
    encode_text,
)
from app.core.response_compression import AdaptiveCompressionMiddleware, choose_encoding, compress_response


def test_large_text_round_trips_through_zstd_envelope():
    original = "tender eligibility and compliance matrix\n" * 500
    encoded = encode_text(original)
    assert encoded.startswith(TEXT_PREFIX)
    assert len(encoded) < len(original)
    assert decode_text(encoded) == original


def test_existing_plain_text_remains_backward_compatible():
    assert decode_text("legacy database value") == "legacy database value"


def test_json_round_trip_preserves_unicode():
    value = {"currency": "INR", "requirements": ["GST", "turnover"] * 200}
    assert decode_json(encode_json(value)) == value


def test_textual_files_compress_but_pdf_stays_identity():
    text = (b'{"tender":"works","state":"Telangana"}\n' * 500)
    encoded_text = encode_bytes(text, content_type="application/json", filename="tenders.json")
    assert encoded_text.encoding == "zstd"
    assert encoded_text.stored_size < encoded_text.original_size
    assert decode_bytes(encoded_text.data, encoded_text.encoding) == text

    pdf = b"%PDF-1.7" + bytes(range(256)) * 30
    encoded_pdf = encode_bytes(pdf, content_type="application/pdf", filename="notice.pdf")
    assert encoded_pdf.encoding == "identity"


def test_api_encoding_prefers_zstd_then_brotli():
    assert choose_encoding("gzip, br, zstd") == "zstd"
    assert choose_encoding("gzip, br") == "br"
    assert choose_encoding("gzip") == "gzip"
    payload = json.dumps({"items": ["tender"] * 500}).encode()
    assert len(compress_response(payload, "zstd")) < len(payload)


def test_api_middleware_compresses_json_response():
    payload = json.dumps({"items": ["tender"] * 500}).encode()

    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": payload, "more_body": False})

    messages = []

    async def send(message):
        messages.append(message)

    async def run():
        middleware = AdaptiveCompressionMiddleware(application, minimum_size=100)
        await middleware(
            {"type": "http", "method": "GET", "headers": [(b"accept-encoding", b"zstd")]},
            lambda: None,
            send,
        )

    asyncio.run(run())
    headers = dict(messages[0]["headers"])
    assert headers[b"content-encoding"] == b"zstd"
    assert decode_bytes(messages[1]["body"], "zstd") == payload


def test_api_middleware_does_not_buffer_event_streams():
    async def application(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
        await send({"type": "http.response.body", "body": b"data: first\n\n", "more_body": True})
        await send({"type": "http.response.body", "body": b"data: second\n\n", "more_body": False})

    messages = []

    async def send(message):
        messages.append(message)

    async def run():
        middleware = AdaptiveCompressionMiddleware(application)
        await middleware(
            {"type": "http", "method": "GET", "headers": [(b"accept-encoding", b"zstd")]},
            lambda: None,
            send,
        )

    asyncio.run(run())
    assert [message["type"] for message in messages] == [
        "http.response.start", "http.response.body", "http.response.body"
    ]
    assert b"content-encoding" not in dict(messages[0]["headers"])
