"""S3/R2 upload storage backend (docs/28 §2 item 8) — against a fake S3 client."""

from __future__ import annotations

from pathlib import Path

from arbiter_api.storage import S3Storage


class _FakeS3:
    """The five methods S3Storage touches, backed by an in-memory dict."""

    def __init__(self) -> None:
        self.obj: dict[str, bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:  # noqa: N803
        self.obj[Key] = Body

    def list_objects_v2(self, *, Bucket: str, Prefix: str, Delimiter: str | None = None):  # noqa: N803
        keys = [k for k in self.obj if k.startswith(Prefix)]
        if Delimiter:
            prefixes = sorted(
                {Prefix + k[len(Prefix) :].split(Delimiter, 1)[0] + Delimiter for k in keys}
            )
            return {"CommonPrefixes": [{"Prefix": p} for p in prefixes]}
        return {"Contents": [{"Key": k} for k in keys]}

    def download_file(self, Bucket: str, Key: str, dest: str) -> None:  # noqa: N803
        Path(dest).write_bytes(self.obj[Key])


def _store(tmp_path: Path) -> S3Storage:
    return S3Storage("arb-bucket", prefix="uploads", cache=tmp_path / "cache", client=_FakeS3())


def test_save_then_path_round_trips_through_the_object_store(tmp_path):
    s = _store(tmp_path)
    uid = s.save("acme", [("bank.csv", b"a,b\n1,2\n"), ("ledger.csv", b"x\n1\n")])
    p = s.path("acme", uid)
    assert p is not None and p.is_dir()
    assert (p / "bank.csv").read_bytes() == b"a,b\n1,2\n"
    assert sorted(f.name for f in p.iterdir()) == ["bank.csv", "ledger.csv"]


def test_list_ids_is_tenant_scoped(tmp_path):
    s = _store(tmp_path)
    a = s.save("acme", [("f.csv", b"1\n")])
    s.save("beta", [("f.csv", b"1\n")])
    assert s.list_ids("acme") == [a]


def test_path_is_none_for_an_unknown_upload(tmp_path):
    assert _store(tmp_path).path("acme", "nope") is None


def test_rejects_a_bad_suffix(tmp_path):
    import pytest
    from arbiter_api.storage import UploadError

    with pytest.raises(UploadError):
        _store(tmp_path).save("acme", [("notes.txt", b"hi")])
