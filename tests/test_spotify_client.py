from unittest.mock import MagicMock, patch

import pytest

from tinyscreen.spotify_auth import SpotifyToken
from tinyscreen.spotify_client import NowPlaying, SpotifyClient, build_spotify_client, parse_currently_playing

TRACK_BODY = {
    "is_playing": True,
    "currently_playing_type": "track",
    "item": {
        "id": "track123",
        "name": "Blinding Lights",
        "artists": [{"name": "The Weeknd"}],
        "album": {
            "images": [
                {"url": "https://example.com/small.jpg", "width": 64},
                {"url": "https://example.com/large.jpg", "width": 640},
            ]
        },
    },
}


def test_parse_currently_playing_204_means_nothing_playing():
    assert parse_currently_playing(204, None) is None


def test_parse_currently_playing_200_with_null_item_means_nothing_playing():
    assert parse_currently_playing(200, {"item": None, "is_playing": False}) is None


def test_parse_currently_playing_200_paused_means_nothing_playing():
    body = {**TRACK_BODY, "is_playing": False}
    assert parse_currently_playing(200, body) is None


def test_parse_currently_playing_episode_type_falls_through_to_nothing_playing():
    body = {**TRACK_BODY, "currently_playing_type": "episode"}
    assert parse_currently_playing(200, body) is None


def test_parse_currently_playing_no_album_images_means_nothing_to_show():
    body = {
        "is_playing": True,
        "currently_playing_type": "track",
        "item": {"id": "x", "name": "No Art", "artists": [{"name": "Someone"}], "album": {"images": []}},
    }
    assert parse_currently_playing(200, body) is None


def test_parse_currently_playing_valid_track_picks_largest_image_and_joins_artists():
    body = {
        **TRACK_BODY,
        "item": {
            **TRACK_BODY["item"],
            "artists": [{"name": "Artist A"}, {"name": "Artist B"}],
        },
    }
    result = parse_currently_playing(200, body)

    assert result == NowPlaying(
        track_id="track123",
        track_name="Blinding Lights",
        artist_name="Artist A, Artist B",
        album_art_url="https://example.com/large.jpg",
    )


def test_build_spotify_client_returns_none_without_credentials():
    from types import SimpleNamespace

    settings = SimpleNamespace(spotify_client_id=None, spotify_client_secret=None)
    assert build_spotify_client(settings) is None


def test_build_spotify_client_returns_client_with_credentials():
    from types import SimpleNamespace

    settings = SimpleNamespace(
        spotify_client_id="id",
        spotify_client_secret="secret",
        spotify_token_cache_path="/tmp/does-not-matter.json",
    )
    with patch("tinyscreen.spotify_client.spotify_auth.load_token", return_value=None):
        client = build_spotify_client(settings)
    assert isinstance(client, SpotifyClient)


def _client_with_token(tmp_path, expires_at=9e18):
    token = SpotifyToken(access_token="valid-access", refresh_token="refresh-tok", expires_at=expires_at)
    with patch("tinyscreen.spotify_client.spotify_auth.load_token", return_value=token):
        client = SpotifyClient("id", "secret", tmp_path / "token.json")
    return client


def test_get_currently_playing_raises_clear_error_without_cached_token(tmp_path):
    with patch("tinyscreen.spotify_client.spotify_auth.load_token", return_value=None):
        client = SpotifyClient("id", "secret", tmp_path / "token.json")

    with pytest.raises(RuntimeError, match="spotify_login.py"):
        client.get_currently_playing()


def test_get_currently_playing_success(tmp_path):
    client = _client_with_token(tmp_path)
    response = MagicMock(status_code=200)
    response.json.return_value = TRACK_BODY
    response.raise_for_status.return_value = None

    with patch("tinyscreen.spotify_client.requests.get", return_value=response) as mock_get:
        result = client.get_currently_playing()

    assert result.track_name == "Blinding Lights"
    _, kwargs = mock_get.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer valid-access"


def test_get_currently_playing_retries_once_on_401(tmp_path):
    client = _client_with_token(tmp_path)

    unauthorized = MagicMock(status_code=401)
    ok = MagicMock(status_code=200)
    ok.json.return_value = TRACK_BODY
    ok.raise_for_status.return_value = None

    new_token = SpotifyToken(access_token="refreshed-access", refresh_token="refresh-tok", expires_at=9e18)

    with (
        patch("tinyscreen.spotify_client.requests.get", side_effect=[unauthorized, ok]),
        patch("tinyscreen.spotify_client.spotify_auth.refresh_access_token", return_value=new_token) as mock_refresh,
        patch("tinyscreen.spotify_client.spotify_auth.save_token"),
    ):
        result = client.get_currently_playing()

    assert result.track_name == "Blinding Lights"
    mock_refresh.assert_called_once()


def test_get_currently_playing_204_returns_none(tmp_path):
    client = _client_with_token(tmp_path)
    response = MagicMock(status_code=204)

    with patch("tinyscreen.spotify_client.requests.get", return_value=response):
        assert client.get_currently_playing() is None


def test_get_currently_playing_429_backs_off_and_returns_none(tmp_path):
    client = _client_with_token(tmp_path)
    response = MagicMock(status_code=429, headers={"Retry-After": "0"})

    with (
        patch("tinyscreen.spotify_client.requests.get", return_value=response),
        patch("tinyscreen.spotify_client.time.sleep") as mock_sleep,
    ):
        assert client.get_currently_playing() is None
    mock_sleep.assert_called_once()
