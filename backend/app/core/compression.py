"""Transparent compression primitives for persisted payloads and API responses."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass

try:  # Python 3.14+
    from compression import zstd as _zstd

    def _compress(data: bytes, level: int = 6) -> bytes:
        return _zstd.compress(data, level=level)

    def _decompress(data: bytes) -> bytes:
        return _zstd.decompress(data)
except ImportError:  # Python 3.12 production image
    import zstandard as _zstandard

    def _compress(data: bytes, level: int = 6) -> bytes:
        return _zstandard.ZstdCompressor(level=level).compress(data)

    def _decompress(data: bytes) -> bytes:
        return _zstandard.ZstdDecompressor().decompress(data)


TEXT_PREFIX = "zstd:v1:"
MIN_TEXT_BYTES = 1024
MIN_BINARY_BYTES = 4096
MIN_SAVINGS_RATIO = 0.08
COMPRESSIBLE_EXTENSIONS = {
    ".txt", ".json", ".jsonl", ".html", ".htm", ".xml", ".csv", ".md", ".log",
}
COMPRESSIBLE_TYPES = {
    "application/json", "application/xml", "application/xhtml+xml", "text/csv",
    "text/html", "text/markdown", "text/plain", "text/xml",
}


@dataclass(frozen=True)
class EncodedBytes:
    data: bytes
    encoding: str
    original_size: int
    stored_size: int
    sha256: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _worth_compressing(original_size: int, compressed_size: int) -> bool:
    return original_size > 0 and compressed_size <= original_size * (1 - MIN_SAVINGS_RATIO)


def encode_text(value: str, *, minimum_bytes: int = MIN_TEXT_BYTES) -> str:
    """Store large text in an ASCII-safe, versioned zstd envelope.

    Existing unprefixed database values remain readable, so rollout does not
    require an eager migration or downtime.
    """
    if not value or value.startswith(TEXT_PREFIX):
        return value
    raw = value.encode("utf-8")
    if len(raw) < minimum_bytes:
        return value
    compressed = _compress(raw)
    envelope = TEXT_PREFIX + base64.b64encode(compressed).decode("ascii")
    if len(envelope.encode("ascii")) >= len(raw) or not _worth_compressing(len(raw), len(compressed)):
        return value
    return envelope


def decode_text(value: str | None) -> str:
    if not value:
        return value or ""
    if not value.startswith(TEXT_PREFIX):
        return value
    payload = base64.b64decode(value[len(TEXT_PREFIX):], validate=True)
    return _decompress(payload).decode("utf-8")


def encode_json(value: object) -> str:
    return encode_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def decode_json(value: str | None, default=None):
    if not value:
        return default
    return json.loads(decode_text(value))


def is_compressible(*, content_type: str = "", filename: str = "") -> bool:
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return normalized_type.startswith("text/") or normalized_type in COMPRESSIBLE_TYPES or suffix in COMPRESSIBLE_EXTENSIONS


def encode_bytes(data: bytes, *, content_type: str = "", filename: str = "") -> EncodedBytes:
    checksum = sha256_bytes(data)
    if len(data) < MIN_BINARY_BYTES or not is_compressible(content_type=content_type, filename=filename):
        return EncodedBytes(data, "identity", len(data), len(data), checksum)
    compressed = _compress(data)
    if not _worth_compressing(len(data), len(compressed)):
        return EncodedBytes(data, "identity", len(data), len(data), checksum)
    return EncodedBytes(compressed, "zstd", len(data), len(compressed), checksum)


def decode_bytes(data: bytes, encoding: str) -> bytes:
    if encoding in {"", "identity", None}:
        return data
    if encoding == "zstd":
        return _decompress(data)
    raise ValueError(f"Unsupported content encoding: {encoding}")
