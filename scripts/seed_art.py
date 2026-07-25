#!/usr/bin/env python3
"""One-time (or occasional) seed script: downloads Mark Rothko's painting
catalog from WikiArt into assets/art/mark-rothko/ for the idle-mode art
rotation.

Run this manually, not as part of the app. The running app (tinyscreen/art.py)
only ever reads the local manifest.json this script writes - it never talks
to WikiArt itself.

Usage:
    uv run python scripts/seed_art.py                 # fetch the whole catalog
    uv run python scripts/seed_art.py --limit 30       # fetch a smaller set

Safe to re-run: paintings already listed in manifest.json are skipped, so a
re-run only fetches anything new (or resumes one that was interrupted).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "tiny-screen-art-seeder/0.1 "
    "(personal home LED-matrix display project, one-time catalog fetch)"
)
LIST_URL = "https://www.wikiart.org/en/mark-rothko/all-works/text-list"
BASE_URL = "https://www.wikiart.org"
REQUEST_DELAY_SECONDS = 1.0


def fetch(url: str) -> requests.Response:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    response.raise_for_status()
    return response


def list_painting_slugs() -> list[str]:
    html = fetch(LIST_URL).text
    soup = BeautifulSoup(html, "html.parser")

    slugs: list[str] = []
    seen: set[str] = set()
    for link in soup.select("a[href^='/en/mark-rothko/']"):
        slug = link["href"].rsplit("/", 1)[-1]
        if not slug or slug in seen or slug == "all-works":
            continue
        seen.add(slug)
        slugs.append(slug)
    return slugs


def fetch_painting_meta(slug: str) -> dict | None:
    url = f"{BASE_URL}/en/mark-rothko/{slug}"
    html = fetch(url).text
    soup = BeautifulSoup(html, "html.parser")

    def meta(prop: str) -> str | None:
        tag = soup.find("meta", property=prop)
        return tag["content"] if tag else None

    image_url = meta("og:image")
    if not image_url:
        return None

    title = meta("og:title") or slug
    title = re.sub(r"\s*-\s*Mark Rothko\s*-\s*WikiArt\.org\s*$", "", title).strip()

    return {"slug": slug, "title": title, "image_url": image_url, "source_url": url}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed assets/art/mark-rothko/ from WikiArt.")
    parser.add_argument(
        "--limit",
        type=int,
        default=157,
        help="Max number of paintings to fetch (default: the full catalog, 157).",
    )
    parser.add_argument(
        "--art-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "assets" / "art" / "mark-rothko",
    )
    args = parser.parse_args()

    art_dir = args.art_dir
    art_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = art_dir / "manifest.json"

    manifest: list[dict] = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    known_slugs = {entry["slug"] for entry in manifest}

    print("Fetching painting list from WikiArt...")
    slugs = list_painting_slugs()[: args.limit]
    print(f"Found {len(slugs)} paintings to consider (limit={args.limit}).")

    for i, slug in enumerate(slugs, start=1):
        if slug in known_slugs:
            print(f"[{i}/{len(slugs)}] {slug}: already have it, skipping")
            continue

        try:
            meta = fetch_painting_meta(slug)
            time.sleep(REQUEST_DELAY_SECONDS)
            if meta is None:
                print(f"[{i}/{len(slugs)}] {slug}: no image found, skipping")
                continue

            ext = Path(meta["image_url"]).suffix or ".jpg"
            filename = f"{slug}{ext}"
            image_bytes = fetch(meta["image_url"]).content
            time.sleep(REQUEST_DELAY_SECONDS)
            (art_dir / filename).write_bytes(image_bytes)

            manifest.append(
                {
                    "slug": slug,
                    "title": meta["title"],
                    "filename": filename,
                    "source_url": meta["source_url"],
                }
            )
            # Write after every painting (not just at the end) so an
            # interrupted run doesn't lose progress already made.
            manifest_path.write_text(json.dumps(manifest, indent=2))
            print(
                f"[{i}/{len(slugs)}] {slug}: saved ({len(image_bytes) // 1024}KB) - {meta['title']}"
            )
        except requests.RequestException as exc:
            print(f"[{i}/{len(slugs)}] {slug}: request failed ({exc}), skipping", file=sys.stderr)

    print(f"Done. {len(manifest)} paintings in manifest at {manifest_path}.")


if __name__ == "__main__":
    main()
