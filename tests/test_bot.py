import json

import pytest

import simplify_discord_webhook as bot


def sample_job(**overrides):
    job = {
        "id": "job-1",
        "company_name": "Example Co",
        "title": "Software Engineer Intern",
        "locations": ["Remote"],
        "url": "https://example.com/apply",
        "active": True,
        "is_visible": True,
        "terms": ["Summer 2027"],
        "date_posted": 1_800_000_000,
    }
    job.update(overrides)
    return job


def test_job_key_prefers_upstream_id():
    assert bot.job_key(sample_job()) == "id:job-1"


def test_job_key_fallback_is_stable():
    first = sample_job(id=None)
    second = dict(reversed(list(first.items())))
    assert bot.job_key(first) == bot.job_key(second)
    assert bot.job_key(first).startswith("sha256:")


def test_corrupt_state_fails_closed(tmp_path, monkeypatch):
    state = tmp_path / "seen.json"
    state.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(bot, "STATE_FILE", state)
    with pytest.raises(RuntimeError, match="refusing to resend"):
        bot.load_seen()


def test_first_run_baselines_without_sending(tmp_path, monkeypatch):
    state = tmp_path / "seen.json"
    monkeypatch.setattr(bot, "STATE_FILE", state)
    monkeypatch.setattr(bot, "SEND_EXISTING_ON_FIRST_RUN", False)
    monkeypatch.setattr(bot, "fetch_jobs", lambda: [sample_job()])
    monkeypatch.setattr(bot, "post_job", lambda job: pytest.fail("Discord called"))
    assert bot.run_once() == 0
    assert json.loads(state.read_text(encoding="utf-8"))["seen"] == ["id:job-1"]


def test_existing_job_is_not_posted_twice(tmp_path, monkeypatch):
    state = tmp_path / "seen.json"
    monkeypatch.setattr(bot, "STATE_FILE", state)
    monkeypatch.setattr(bot, "DRY_RUN", False)
    monkeypatch.setattr(bot, "fetch_jobs", lambda: [sample_job()])
    bot.save_seen({"id:job-1"})
    sent = []
    monkeypatch.setattr(bot, "post_job", sent.append)
    assert bot.run_once() == 0
    assert sent == []


def test_dry_run_never_calls_discord_or_changes_state(tmp_path, monkeypatch):
    state = tmp_path / "seen.json"
    monkeypatch.setattr(bot, "STATE_FILE", state)
    monkeypatch.setattr(bot, "DRY_RUN", True)
    monkeypatch.setattr(bot, "fetch_jobs", lambda: [sample_job()])
    bot.save_seen(set())
    before = state.read_text(encoding="utf-8")
    monkeypatch.setattr(bot, "post_job", lambda job: pytest.fail("Discord called"))
    assert bot.run_once() == 1
    assert state.read_text(encoding="utf-8") == before
