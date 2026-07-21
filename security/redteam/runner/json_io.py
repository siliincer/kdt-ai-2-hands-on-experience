"""Bounded JSON decoding for local HTTP response streams."""

from __future__ import annotations

import json
from collections.abc import Iterable


def decode_bounded_json(chunks: Iterable[bytes], max_bytes: int) -> object:
    content = bytearray()
    for chunk in chunks:
        content.extend(chunk)
        if len(content) > max_bytes:
            raise ValueError("JSON response exceeded the configured byte limit")
    return json.loads(content)
