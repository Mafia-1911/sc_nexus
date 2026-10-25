"""Turn non-JSON bodies into JSON-able data so schema inference and profiling work on them."""

from __future__ import annotations

import csv
import io
import re
import time
import zipfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

import feedparser
import openpyxl

_INT = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")


def coerce(text: str) -> Any:
    """CSV cell to int/float/str, leaving codes with leading zeros as strings."""
    if text == "":
        return None
    digits = text.lstrip("-")
    if len(digits) > 1 and digits[0] == "0" and digits[1] != ".":
        return text  # zero-padded code (CAMEO "04", FIPS "06"), not a number
    if _INT.match(text):
        return int(text)
    if _FLOAT.match(text):
        try:
            return float(text)
        except ValueError:
            return text
    return text


def text_of(body: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def csv_records(
    body: bytes,
    *,
    delimiter: str = ",",
    columns: Sequence[str] | None = None,
    text_columns: Sequence[str] = (),
    limit: int | None = 5000,
) -> list[dict[str, Any]]:
    """Rows as dicts. With `columns`, the file has no header row (e.g. GDELT exports).

    `text_columns` are never coerced: code columns must keep one type ("04" and "14" alike).
    """
    reader = csv.reader(io.StringIO(text_of(body)), delimiter=delimiter)
    header = list(columns) if columns else next(reader, [])
    keep = set(text_columns)
    rows = []
    for i, row in enumerate(reader):
        if limit is not None and i >= limit:
            break
        rows.append(
            {
                h: (v.strip() or None) if h in keep else coerce(v.strip())
                for h, v in zip(header, row, strict=False)
            }
        )
    return rows


def csv_decoder(**kwargs: Any) -> Callable[[bytes], list[dict[str, Any]]]:
    return lambda body: csv_records(body, **kwargs)


def _jsonable(value: Any) -> Any:
    if isinstance(value, time.struct_time):
        return datetime(*value[:6], tzinfo=UTC).isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def rss(body: bytes) -> dict[str, Any]:
    """Feed metadata and entries as parsed by feedparser (RSS 0.9x/1.0/2.0, Atom)."""
    parsed = feedparser.parse(body)
    return {
        "bozo": bool(parsed.bozo),
        "bozo_exception": str(parsed.get("bozo_exception", "")) or None,
        "version": parsed.get("version"),
        "feed": _jsonable(dict(parsed.feed)),
        "entries": [_jsonable(dict(e)) for e in parsed.entries],
    }


def zip_listing(body: bytes) -> list[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        return [
            {
                "name": info.filename,
                "size": info.file_size,
                "compressed": info.compress_size,
                "modified": datetime(*info.date_time).isoformat(),
            }
            for info in zf.infolist()
        ]


def zip_member(body: bytes, pattern: str = r".*") -> bytes:
    """Bytes of the first member whose name matches `pattern`."""
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        for name in zf.namelist():
            if re.search(pattern, name):
                return zf.read(name)
    raise KeyError(f"no zip member matches {pattern!r}")


def zip_csv_decoder(pattern: str = r"\.csv$", **kwargs: Any) -> Callable[[bytes], Any]:
    return lambda body: csv_records(zip_member(body, pattern), **kwargs)


def xlsx_outline(body: bytes, preview_rows: int = 8) -> dict[str, Any]:
    """Sheet names, dimensions and the first non-empty rows of each sheet."""
    wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    sheets = {}
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [c for c in row if c not in (None, "")]
            if cells:
                rows.append(
                    [_jsonable(c) if not isinstance(c, datetime) else c.isoformat() for c in row]
                )
            if len(rows) >= preview_rows:
                break
        sheets[ws.title] = {"dimensions": ws.calculate_dimension(), "preview": rows}
    wb.close()
    return {"sheets": sheets}


class _Outline(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.links: list[dict[str, str]] = []
        self._in_title = False
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._href:
            self.links.append({"href": self._href, "text": " ".join("".join(self._text).split())})
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._href is not None:
            self._text.append(data)


def html_outline(body: bytes) -> dict[str, Any]:
    parser = _Outline()
    parser.feed(text_of(body))
    return {"title": parser.title.strip(), "links": parser.links}
