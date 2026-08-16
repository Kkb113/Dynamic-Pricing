from __future__ import annotations

import json

import pytest

from phase5 import runner


def test_test_lock_requires_valid_spec(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ARTIFACTS", tmp_path)
    with pytest.raises(RuntimeError, match="REQUIRED"):
        runner._require_frozen_spec()
    payload = {"one": 1}
    payload["frozen_quantity_spec_sha256"] = runner._json_hash({"one": 1})
    (tmp_path / "frozen_quantity_spec.json").write_text(json.dumps(payload), encoding="utf-8")
    assert runner._require_frozen_spec()["one"] == 1
    payload["one"] = 2
    (tmp_path / "frozen_quantity_spec.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="HASH"):
        runner._require_frozen_spec()

