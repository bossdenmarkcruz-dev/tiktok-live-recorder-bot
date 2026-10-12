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


def test_delete_job_files_keeps_unrelated_recordings(tmp_path, monkeypatch):
    monkeypatch.setattr(worker.settings, "recordings_dir", str(tmp_path))
    job_id = "job-one"
    files = [f"{job_id}.mp4", f"{job_id}-telegram.mp4", f"{job_id}.log", "job-two.mp4"]
    for name in files:
        (tmp_path / name).write_bytes(b"test")

    worker.delete_job_files(job_id)

    assert not (tmp_path / f"{job_id}.mp4").exists()
    assert not (tmp_path / f"{job_id}-telegram.mp4").exists()
    assert not (tmp_path / f"{job_id}.log").exists()
    assert (tmp_path / "job-two.mp4").exists()
