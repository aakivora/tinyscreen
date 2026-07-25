from unittest.mock import MagicMock, patch

from tinyscreen.spotify_auth import (
    SpotifyToken,
    build_authorize_url,
    exchange_code_for_token,
    is_expired,
    load_token,
    refresh_access_token,
    save_token,
)


def test_is_expired():
    token = SpotifyToken(access_token="a", refresh_token="r", expires_at=1000.0)
    assert is_expired(token, now=1000.0) is True
    assert is_expired(token, now=1000.1) is True
    assert is_expired(token, now=999.9) is False


def test_build_authorize_url_includes_scope_and_state():
    url = build_authorize_url("client123", "http://127.0.0.1:8901/callback", "state456")
    assert url.startswith("https://accounts.spotify.com/authorize?")
    assert "client_id=client123" in url
    assert "state=state456" in url
    assert "scope=user-read-currently-playing" in url
    assert "redirect_uri=" in url


def _fake_token_response(access_token="new-access", refresh_token="new-refresh", expires_in=3600):
    response = MagicMock()
    response.raise_for_status.return_value = None
    body = {"access_token": access_token, "expires_in": expires_in}
    if refresh_token is not None:
        body["refresh_token"] = refresh_token
    response.json.return_value = body
    return response


def test_exchange_code_for_token_posts_expected_form_and_basic_auth():
    with patch("tinyscreen.spotify_auth.requests.post", return_value=_fake_token_response()) as mock_post:
        token = exchange_code_for_token("client123", "secret456", "auth-code", "http://127.0.0.1:8901/callback")

    assert token.access_token == "new-access"
    assert token.refresh_token == "new-refresh"
    assert token.expires_at > 0

    _, kwargs = mock_post.call_args
    assert kwargs["data"] == {
        "grant_type": "authorization_code",
        "code": "auth-code",
        "redirect_uri": "http://127.0.0.1:8901/callback",
    }
    assert kwargs["headers"]["Authorization"].startswith("Basic ")


def test_refresh_access_token_preserves_old_refresh_token_when_response_omits_it():
    # Spotify's refresh responses often don't include a new refresh_token -
    # the old one should keep being used, not get silently dropped.
    response = _fake_token_response(refresh_token=None)
    with patch("tinyscreen.spotify_auth.requests.post", return_value=response):
        token = refresh_access_token("client123", "secret456", "still-valid-refresh-token")

    assert token.refresh_token == "still-valid-refresh-token"


def test_save_and_load_token_roundtrip(tmp_path):
    path = tmp_path / "nested" / "spotify_token.json"
    original = SpotifyToken(access_token="a", refresh_token="r", expires_at=12345.0)

    save_token(path, original)
    loaded = load_token(path)

    assert loaded == original


def test_load_token_returns_none_when_no_cache_exists(tmp_path):
    assert load_token(tmp_path / "does-not-exist.json") is None
