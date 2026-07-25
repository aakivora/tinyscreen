"""Polls Spotify's currently-playing endpoint and decides what the display
should show as a result.

Two layers, mirroring tinyscreen/weather.py's split: `parse_currently_playing`
is a pure function (easy to test against every response shape Spotify can
send) with no network/token knowledge; `SpotifyClient` handles the actual
HTTP call, token refresh, and the 401/429 resilience the reference project's
own client established as the right approach.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from tinyscreen import spotify_auth
from tinyscreen.spotify_auth import SpotifyToken

CURRENTLY_PLAYING_URL = "https://api.spotify.com/v1/me/player/currently-playing"


@dataclass
class NowPlaying:
    track_id: str  # Spotify track ID - a more reliable change-detection key
    # than name/artist strings (handles e.g. remixes or covers that share a
    # title, and is what app.py uses to decide whether to re-download art).
    track_name: str
    artist_name: str
    album_art_url: str


def parse_currently_playing(status_code: int, body: dict[str, Any] | None) -> NowPlaying | None:
    """Spotify has (at least) three different ways of saying "nothing's
    playing": an empty 204 response, a 200 with `item: null`, and a 200
    with a real item but `is_playing: false` (e.g. paused). All three mean
    the same thing here - only a genuinely-playing track produces a result.
    Episodes/ads/unknown content types fall through to "nothing playing"
    too, for this phase - this project's Spotify mode is about music, and
    extending it to podcasts later is a small, separate decision.
    """
    if status_code == 204 or body is None:
        return None

    item = body.get("item")
    if item is None or not body.get("is_playing", False):
        return None

    if body.get("currently_playing_type") != "track":
        return None

    images = item.get("album", {}).get("images", [])
    if not images:
        # No album art to show is, for this display, the same as nothing
        # playing - the whole point of Spotify mode is the artwork.
        return None
    album_art_url = max(images, key=lambda image: image.get("width") or 0)["url"]

    artist_name = ", ".join(artist["name"] for artist in item.get("artists", []))

    return NowPlaying(
        track_id=item.get("id", ""),
        track_name=item.get("name", ""),
        artist_name=artist_name,
        album_art_url=album_art_url,
    )


def should_show_spotify(
    is_playing: bool, last_playing_at: float | None, now: float, fallback_seconds: float
) -> bool:
    """Switches to Spotify mode the instant something's playing, but only
    falls back to idle mode after `fallback_seconds` of nothing playing -
    so a brief gap between songs doesn't bounce the display back and forth.
    `last_playing_at`/`now` are time.monotonic()-based, like the rest of
    this project's in-process timing (see weather.py's fetched_at)."""
    if is_playing:
        return True
    if last_playing_at is None:
        return False
    return (now - last_playing_at) < fallback_seconds


class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str, token_cache_path) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_cache_path = token_cache_path
        self._token: SpotifyToken | None = spotify_auth.load_token(token_cache_path)

    def _ensure_fresh_token(self) -> str:
        if self._token is None:
            raise RuntimeError(
                "No cached Spotify token found. Run `uv run python scripts/spotify_login.py` "
                "once to authorize this app with your Spotify account."
            )
        if spotify_auth.is_expired(self._token):
            self._token = spotify_auth.refresh_access_token(
                self.client_id, self.client_secret, self._token.refresh_token
            )
            spotify_auth.save_token(self.token_cache_path, self._token)
        return self._token.access_token

    def _fetch(self, access_token: str) -> requests.Response:
        return requests.get(
            CURRENTLY_PLAYING_URL,
            params={"additional_types": "track,episode"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

    def get_currently_playing(self) -> NowPlaying | None:
        access_token = self._ensure_fresh_token()
        response = self._fetch(access_token)

        if response.status_code == 401:
            # The token looked fresh by our own expiry math but Spotify
            # rejected it anyway (e.g. revoked) - refresh once and retry
            # rather than erroring out for the rest of the poll interval.
            self._token = spotify_auth.refresh_access_token(
                self.client_id, self.client_secret, self._token.refresh_token
            )
            spotify_auth.save_token(self.token_cache_path, self._token)
            response = self._fetch(self._token.access_token)

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", 5))
            time.sleep(max(1.0, retry_after))
            return None

        if response.status_code == 204:
            return None

        response.raise_for_status()
        return parse_currently_playing(response.status_code, response.json())


def build_spotify_client(settings) -> SpotifyClient | None:
    """Returns None whenever Spotify isn't configured, so app.py can skip
    polling entirely - the same structural "no secrets, no problem" pattern
    build_weather_client() already established."""
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        return None
    return SpotifyClient(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        token_cache_path=settings.spotify_token_cache_path,
    )
