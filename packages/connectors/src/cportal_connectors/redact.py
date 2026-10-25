"""Strip credentials from anything the harness writes (AGENTS.md rule 8)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MASK = "***REDACTED***"
_SECRET_NAME = re.compile(
    r"(?i)(^|[_\-.])(api[_\-]?key|apikey|key|token|access[_\-]?token|secret|password|passwd|"
    r"authorization|subscription[_\-]key)$"
)


def is_secret_name(name: str) -> bool:
    return bool(_SECRET_NAME.search(name))


class Redactor:
    """Masks secret-looking names and every known secret value wherever it appears."""

    def __init__(self, secret_values: Iterable[str]) -> None:
        # Longest first, so a secret that contains another is masked whole.
        self._values = sorted(
            {v for v in secret_values if v and len(v) >= 4}, key=len, reverse=True
        )

    def text(self, value: str) -> str:
        for secret in self._values:
            value = value.replace(secret, MASK)
        return value

    def bytes(self, value: bytes) -> bytes:
        for secret in self._values:
            value = value.replace(secret.encode(), MASK.encode())
        return value

    def url(self, url: str) -> str:
        parts = urlsplit(url)
        query = [(k, MASK if is_secret_name(k) else v) for k, v in parse_qsl(parts.query, True)]
        return self.text(urlunsplit(parts._replace(query=urlencode(query, safe=":,;[]()"))))

    def mapping(self, data: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        return {k: (MASK if is_secret_name(k) else self.value(v)) for k, v in data.items()}

    def value(self, data: Any) -> Any:
        if isinstance(data, Mapping):
            return self.mapping(data)
        if isinstance(data, list | tuple):
            return [self.value(v) for v in data]
        if isinstance(data, str):
            return self.text(data)
        return data
