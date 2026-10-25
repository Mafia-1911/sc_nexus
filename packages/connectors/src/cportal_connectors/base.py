"""Connector contract shared by every DS-ID module, plus the per-source token bucket.

M0 implements `probe()` only (03-data-sources.md §3). `fetch_raw()`, `parse()` and the synthetic
twin join the contract in M1, once the canonical schema is fixed at G1.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Literal

if TYPE_CHECKING:
    from cportal_connectors.harness import ProbeContext

Purpose = Literal[
    "main",  # the minimal meaningful call
    "meta",  # service metadata: layer info, status pages, robots.txt, docs
    "no_key",
    "bad_key",
    "bad_param",
    "empty",
    "last_page",
    "oversized",
    "timeout",
]

FAILURE_PURPOSES: frozenset[str] = frozenset(
    {"no_key", "bad_key", "bad_param", "empty", "last_page", "oversized", "timeout"}
)

Decoder = Callable[[bytes], Any]


@dataclass(frozen=True)
class ProbeCall:
    """One HTTP request in a probe run. Everything about it lands on disk verbatim."""

    name: str
    url: str
    purpose: Purpose = "main"
    method: str = "GET"
    params: Mapping[str, Any] | None = None
    headers: Mapping[str, str] | None = None
    json_body: Any = None
    data: str | bytes | None = None
    timeout_s: float = 60.0
    # Stop reading after this many bytes; the response is marked truncated (big downloads).
    max_bytes: int | None = None
    # Copy the response to data/samples/<DS-ID>/ for replay mode and contract tests.
    sample: bool = False
    # Rewrite the body before it is committed as a sample (e.g. strip full news text).
    sample_transform: Callable[[bytes], bytes] | None = None
    sample_ext: str | None = None  # extension of the transformed sample, if it changes format
    # Path to the record list inside the parsed body, e.g. "features[].attributes".
    records: str | None = None
    # Turns a non-JSON body (CSV, RSS, zip, xlsx) into JSON-able data for schema inference.
    decode: Decoder | None = None
    ext: str | None = None
    note: str = ""
    # Calls sharing a group (e.g. a 24-hour sweep of 15-minute files) collapse into one card row.
    group: str | None = None


@dataclass(frozen=True)
class FieldNote:
    unit: str = ""
    meaning: str = ""


class Connector:
    """Base class: subclasses set the class attributes and implement `probe_calls()`,
    or override `probe()` for WebSocket, file and offline sources."""

    ds_id: ClassVar[str]
    title: ClassVar[str]
    # Env vars the main calls need. When one is missing, `probe()` still runs the calls that
    # work without it (failure modes, metadata) and the CLI lists the source under "needs you".
    needs: ClassVar[tuple[str, ...]] = ()
    # Units and meanings for the card's field table, keyed by "<call>:<field path>".
    field_notes: ClassVar[Mapping[str, FieldNote]] = {}

    def probe_calls(self, ctx: ProbeContext) -> Iterable[ProbeCall]:
        return ()

    def probe(self, ctx: ProbeContext) -> None:
        for call in self.probe_calls(ctx):
            ctx.http(call)


@dataclass
class TokenBucket:
    """Blocking token bucket: `rate` tokens per second, at most `capacity` banked."""

    rate: float
    capacity: float = 1.0
    _tokens: float = field(init=False)
    _last: float = field(init=False)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if self.rate <= 0 or self.capacity < 1:
            raise ValueError("rate must be > 0 and capacity >= 1")
        self._tokens = self.capacity
        self._last = self.clock()

    @classmethod
    def every(cls, min_interval_s: float) -> TokenBucket:
        """At most one request per `min_interval_s` seconds, no bursts."""
        return cls(rate=1.0 / min_interval_s, capacity=1.0)

    def acquire(self) -> float:
        """Take one token, sleeping if needed. Returns the seconds slept."""
        with self._lock:
            now = self.clock()
            self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
            self._last = now
            wait = 0.0
            if self._tokens < 1:
                wait = (1 - self._tokens) / self.rate
                self.sleep(wait)
                self._last = self.clock()
                self._tokens = 1.0
            self._tokens -= 1
            return wait
