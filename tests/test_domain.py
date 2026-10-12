import pytest
from app.domain import InvalidTikTokLiveURL, validate_tiktok_live_url


@pytest.mark.parametrize("url", [
    "https://www.tiktok.com/@creator/live",
    "https://tiktok.com/@creator/live?lang=en",
    "http://m.tiktok.com/@some.creator/live/",
])
def test_accepts_direct_tiktok_live_urls(url):
    assert validate_tiktok_live_url(url) == url


@pytest.mark.parametrize("url", [
    "https://example.com/@creator/live",
    "https://www.tiktok.com/@creator/video/123",
    "https://www.tiktok.com/@creator/foo/live",
    "https://www.tiktok.com.evil.test/@creator/live",
    "file:///etc/passwd",
    "https://user@www.tiktok.com/@creator/live",
    "https://vm.tiktok.com/AbCd/",
])
def test_rejects_non_live_or_unsafe_urls(url):
    with pytest.raises(InvalidTikTokLiveURL):
        validate_tiktok_live_url(url)
