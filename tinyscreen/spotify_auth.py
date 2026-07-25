"""Spotify OAuth: token exchange, refresh, and the on-disk cache that lets
the main app avoid ever needing to open a browser itself.

Standard Authorization Code flow (not PKCE) - same as the tnarla/spotify-matrix
reference this project was inspired by: a `client_secret` plus HTTP Basic
auth at the token endpoint, rather than a public-client PKCE flow. That's
appropriate here because this only ever runs as a script the developer
controls directly (never distributed to other people's machines), which is
exactly the case Authorization Code + secret is designed for.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SCOPE = "user-read-currently-playing"

# Refresh this many seconds before the token actually expires, so a request
# never starts with a token that dies mid-flight.
EXPIRY_SAFETY_MARGIN_SECONDS = 60


@dataclass
class SpotifyToken:
    access_token: str
    refresh_token: str
    expires_at: float  # time.time()-based wall-clock timestamp - this gets
    # persisted to disk and read back after process restarts, so it has to
    # survive that round trip meaningfully; time.monotonic() (used elsewhere
    # in this project for in-process staleness checks) resets on every
    # restart and can't be compared across runs.


def is_expired(token: SpotifyToken, now: float | None = None) -> bool:
    return (now if now is not None else time.time()) >= token.expires_at


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
    }
    query = "&".join(f"{key}={requests.utils.quote(value)}" for key, value in params.items())
    return f"{AUTHORIZE_URL}?{query}"


def _post_token(client_id: str, client_secret: str, data: dict[str, str]) -> SpotifyToken:
    basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = requests.post(
        TOKEN_URL,
        data=data,
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=10,
    )
    response.raise_for_status()
    body = response.json()

    return SpotifyToken(
        access_token=body["access_token"],
        # A refresh response often omits refresh_token (Spotify only sends
        # a new one occasionally) - callers pass the previous one through
        # via `data` having supplied it, but we still need a fallback here
        # for the exchange call, which always has one in the response.
        refresh_token=body.get("refresh_token", data.get("refresh_token", "")),
        expires_at=time.time() + int(body.get("expires_in", 3600)) - EXPIRY_SAFETY_MARGIN_SECONDS,
    )


def exchange_code_for_token(
    client_id: str, client_secret: str, code: str, redirect_uri: str
) -> SpotifyToken:
    return _post_token(
        client_id,
        client_secret,
        {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
    )


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> SpotifyToken:
    return _post_token(
        client_id,
        client_secret,
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
    )


def load_token(path: Path) -> SpotifyToken | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return SpotifyToken(**data)


def save_token(path: Path, token: SpotifyToken) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(token)))
