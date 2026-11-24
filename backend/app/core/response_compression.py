"""ASGI response compression with zstd, Brotli and gzip-compatible fallback."""

from __future__ import annotations

import gzip
import brotli

from app.core.compression import _compress as zstd_compress


COMPRESSIBLE_RESPONSE_TYPES = (
    "application/json", "application/javascript", "application/xml", "image/svg+xml", "text/",
)


def choose_encoding(accept_encoding: str) -> str | None:
    accepted = {part.split(";", 1)[0].strip().lower() for part in accept_encoding.split(",")}
    for encoding in ("zstd", "br", "gzip"):
        if encoding in accepted:
            return encoding
    return None


def compress_response(data: bytes, encoding: str) -> bytes:
    if encoding == "zstd":
        return zstd_compress(data, level=4)
    if encoding == "br":
        return brotli.compress(data, quality=4)
    if encoding == "gzip":
        return gzip.compress(data, compresslevel=5)
    raise ValueError(f"Unsupported response encoding: {encoding}")


class AdaptiveCompressionMiddleware:
    def __init__(self, app, minimum_size: int = 1024):
        self.app = app
        self.minimum_size = minimum_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") == "HEAD":
            await self.app(scope, receive, send)
            return

        request_headers = {k.lower(): v for k, v in scope.get("headers", [])}
        encoding = choose_encoding(request_headers.get(b"accept-encoding", b"").decode("latin-1"))
        if not encoding:
            await self.app(scope, receive, send)
            return

        start = None
        chunks: list[bytes] = []
        bypass = False

        async def capture(message):
            nonlocal start, bypass
            if message["type"] == "http.response.start":
                start = message
                headers = {k.lower(): v for k, v in message.get("headers", [])}
                content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
                compressible = any(content_type.startswith(item) for item in COMPRESSIBLE_RESPONSE_TYPES)
                bypass = (
                    not compressible
                    or content_type.startswith("text/event-stream")
                    or b"content-encoding" in headers
                    or message["status"] in {204, 304}
                )
                if bypass:
                    await send(message)
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            if bypass:
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body", False):
                return

            assert start is not None
            body = b"".join(chunks)
            headers = list(start.get("headers", []))
            header_map = {k.lower(): v for k, v in headers}
            content_type = header_map.get(b"content-type", b"").decode("latin-1").lower()
            compressible = any(content_type.startswith(item) for item in COMPRESSIBLE_RESPONSE_TYPES)
            if len(body) >= self.minimum_size and compressible:
                compressed = compress_response(body, encoding)
                if len(compressed) < len(body):
                    body = compressed
                    headers = [(k, v) for k, v in headers if k.lower() not in {b"content-length", b"etag", b"vary"}]
                    headers.extend([
                        (b"content-encoding", encoding.encode("ascii")),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"vary", b"Accept-Encoding"),
                    ])
                    start["headers"] = headers
            await send(start)
            await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, receive, capture)
