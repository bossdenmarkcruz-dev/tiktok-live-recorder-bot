import json
from types import SimpleNamespace
import pytest
from app import worker


LIVE_INFO = {"extractor_key": "TikTok", "is_live": True, "live_status": "is_live"}


def test_probe_accepts_active_tiktok_live(monkeypatch):
    monkeypatch.setattr(worker.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(LIVE_INFO), stderr=""))
    assert worker.probe_live("https://www.tiktok.com/@creator/live")["is_live"] is True


def test_probe_rejects_non_live(monkeypatch):
    offline = {"extractor_key": "TikTok", "is_live": False, "live_status": "not_live"}
    monkeypatch.setattr(worker.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(offline), stderr=""))
    with pytest.raises(RuntimeError, match="not currently live"):
        worker.probe_live("https://www.tiktok.com/@creator/live")


def test_probe_rejects_non_tiktok_extractor(monkeypatch):
    metadata = {"extractor_key": "SomeSite", "is_live": True}
    monkeypatch.setattr(worker.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(metadata), stderr=""))
    with pytest.raises(RuntimeError, match="did not resolve to a TikTok"):
        worker.probe_live("https://www.tiktok.com/@creator/live")
