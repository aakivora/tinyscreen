#!/usr/bin/env python3
"""One-time interactive Spotify OAuth setup.

Run this once (and again any time the cached refresh token stops working,
e.g. if you revoke access from your Spotify account settings) before
starting the main app with Spotify configured. Opens your browser to
Spotify's consent page, catches the redirect on a short-lived local server,
and caches the resulting token - tinyscreen/spotify_client.py only ever
reads that cache afterward; the main app never opens a browser itself.

Usage:
    uv run python scripts/spotify_login.py
"""

from __future__ import annotations

import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tinyscreen import spotify_auth  # noqa: E402
from tinyscreen.config import load_settings  # noqa: E402


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        params = parse_qs(urlparse(self.path).query)

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        # Browsers sometimes fire off an unrelated request (e.g. favicon.ico)
        # alongside the real redirect - only treat a request carrying
        # "code" or "error" as the actual callback, so a stray request
        # doesn't get mistaken for it.
        if "code" in params or "error" in params:
            self.server.result = params  # type: ignore[attr-defined]
            self.wfile.write(
                b"<html><body>Authorized - you can close this tab and return to the terminal.</body></html>"
            )
        else:
            self.wfile.write(b"<html><body></body></html>")

    def log_message(self, format, *args) -> None:  # silence default request logging
        return


def _wait_for_callback(redirect_uri: str) -> dict[str, list[str]]:
    parsed = urlparse(redirect_uri)
    server = HTTPServer((parsed.hostname or "127.0.0.1", parsed.port or 80), _CallbackHandler)
    server.result = None  # type: ignore[attr-defined]

    print(f"Waiting for Spotify to redirect back to {redirect_uri} ...")
    while server.result is None:  # type: ignore[attr-defined]
        server.handle_request()
    server.server_close()
    return server.result  # type: ignore[attr-defined]


def main() -> None:
    settings = load_settings()

    if not settings.spotify_client_id or not settings.spotify_client_secret:
        print(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET aren't set in .env.\n\n"
            "1. Create an app at https://developer.spotify.com/dashboard\n"
            f"2. Add {settings.spotify_redirect_uri} as a Redirect URI in that app's settings\n"
            "3. Copy its Client ID and Client Secret into .env\n"
            "4. Run this script again"
        )
        raise SystemExit(1)

    state = secrets.token_urlsafe(18)
    auth_url = spotify_auth.build_authorize_url(
        settings.spotify_client_id, settings.spotify_redirect_uri, state
    )

    print(f"Opening your browser to authorize tiny-screen with Spotify:\n{auth_url}\n")
    webbrowser.open(auth_url)

    params = _wait_for_callback(settings.spotify_redirect_uri)

    if "error" in params:
        print(f"Spotify returned an error: {params['error'][0]}")
        raise SystemExit(1)
    if params.get("state", [None])[0] != state:
        print("State didn't match this login attempt (possibly stale/replayed redirect) - try again.")
        raise SystemExit(1)

    code = params["code"][0]
    token = spotify_auth.exchange_code_for_token(
        settings.spotify_client_id,
        settings.spotify_client_secret,
        code,
        settings.spotify_redirect_uri,
    )
    spotify_auth.save_token(settings.spotify_token_cache_path, token)
    print(f"Success! Token cached at {settings.spotify_token_cache_path}")


if __name__ == "__main__":
    main()
