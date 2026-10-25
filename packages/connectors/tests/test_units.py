from __future__ import annotations

import io
import tarfile

import pytest
from cportal_connectors.base import TokenBucket
from cportal_connectors.decoders import coerce, csv_records
from cportal_connectors.redact import MASK, Redactor, is_secret_name
from cportal_connectors.schema import profile_records, resolve_records
from cportal_connectors.vision import tar_members


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_token_bucket_spaces_requests() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate=0.5, capacity=1, clock=clock, sleep=clock.sleep)
    assert bucket.acquire() == 0.0
    assert bucket.acquire() == pytest.approx(2.0)
    clock.now += 10
    assert bucket.acquire() == 0.0


def test_token_bucket_rejects_bad_config() -> None:
    with pytest.raises(ValueError):
        TokenBucket(rate=0, capacity=1)


@pytest.mark.parametrize(
    ("name", "secret"),
    [
        ("api_key", True),
        ("APIKey", True),
        ("Authorization", True),
        ("subscription-key", True),
        ("token", True),
        ("appname", False),
        ("monkey", False),
        ("q", False),
    ],
)
def test_secret_names(name: str, secret: bool) -> None:
    assert is_secret_name(name) is secret


def test_redactor_masks_values_everywhere() -> None:
    r = Redactor(["abcd1234secret"])
    assert r.url(
        "https://x/y?api_key=zzz&q=1"
    ) == f"https://x/y?api_key={MASK.replace('*', '%2A')}&q=1" or MASK in r.url(
        "https://x/y?api_key=zzz&q=1"
    )
    assert r.text("echo abcd1234secret!") == f"echo {MASK}!"
    assert r.value({"nested": ["abcd1234secret"]}) == {"nested": [MASK]}
    assert r.mapping({"Authorization": "Bearer x"}) == {"Authorization": MASK}


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("04", "04"),
        ("4", 4),
        ("-3", -3),
        ("0", 0),
        ("0.5", 0.5),
        ("12.5", 12.5),
        ("", None),
        ("BD MGL", "BD MGL"),
    ],
)
def test_coerce_keeps_codes_as_text(text: str, value: object) -> None:
    assert coerce(text) == value


def test_csv_records_without_header_keeps_code_columns_as_text() -> None:
    rows = csv_records(
        b"1\tBG\t04\n2\tIN\t14\n",
        delimiter="\t",
        columns=["id", "cc", "root"],
        text_columns=["root"],
    )
    assert rows == [{"id": 1, "cc": "BG", "root": "04"}, {"id": 2, "cc": "IN", "root": "14"}]


def test_resolve_records_paths() -> None:
    doc = {"features": [{"attributes": {"a": 1}}, {"attributes": {"a": 2}}]}
    assert resolve_records(doc, "features[].attributes") == [{"a": 1}, {"a": 2}]
    assert resolve_records([{"page": 1}, [{"x": 1}]], "1[]") == [{"x": 1}]
    assert resolve_records([1, 2], "") == [1, 2]
    assert resolve_records(doc, None) is None


def test_profile_records_counts_missing() -> None:
    stats = {s.path: s for s in profile_records([{"a": 1, "b": {"c": "x"}}, {"a": None}])}
    assert stats["a"].null_pct == 50.0
    assert stats["b.c"].null_pct == 50.0
    assert stats["a"].types == "integer"


def test_tar_members_from_partial_head() -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in (("capsules/", b""), ("capsules/a.csv", b"x,y\n")):
            info = tarfile.TarInfo(name)
            if name.endswith("/"):
                info.type = tarfile.DIRTYPE
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    assert tar_members(buf.getvalue()[:4096]) == ["capsules/", "capsules/a.csv"]
