"""Tests for state.atomic_write_json — roundtrip + no leftover tmp."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from state import atomic_write_json


def test_roundtrip_basic(tmp_path: Path):
    target = tmp_path / "state.json"
    payload = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}
    atomic_write_json(target, payload)
    assert target.exists()
    with target.open("r", encoding="utf-8") as f:
        roundtrip = json.load(f)
    assert roundtrip == payload


def test_no_leftover_tmp(tmp_path: Path):
    target = tmp_path / "portfolio.json"
    atomic_write_json(target, {"x": 1})
    # No *.tmp sibling should remain.
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"tmp files leaked: {leftovers}"


def test_overwrite_preserves_atomicity(tmp_path: Path):
    target = tmp_path / "status.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})
    with target.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data == {"v": 2}


def test_handles_datetime_via_default_str(tmp_path: Path):
    target = tmp_path / "with_dt.json"
    dt = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    atomic_write_json(target, {"ts": dt})
    with target.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # default=str renders datetime as its str(); just confirm it's a string and
    # contains the year — the exact format isn't critical for roundtrip integrity.
    assert isinstance(data["ts"], str)
    assert "2024" in data["ts"]


def test_creates_parent_dir(tmp_path: Path):
    nested = tmp_path / "nested" / "deeper" / "out.json"
    atomic_write_json(nested, {"ok": True})
    assert nested.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
