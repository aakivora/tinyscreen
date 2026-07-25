from tinyscreen.spotify_client import should_show_spotify


def test_shows_spotify_immediately_when_playing():
    assert should_show_spotify(is_playing=True, last_playing_at=None, now=100.0, fallback_seconds=90.0) is True


def test_never_shown_before_anything_has_ever_played():
    assert should_show_spotify(is_playing=False, last_playing_at=None, now=100.0, fallback_seconds=90.0) is False


def test_stays_in_spotify_mode_within_fallback_window_after_stopping():
    # Playback stopped at t=100, now it's t=150 (50s later) - well within
    # the 90s grace period, so a track-to-track pause doesn't bounce the
    # display back to idle mode.
    assert (
        should_show_spotify(is_playing=False, last_playing_at=100.0, now=150.0, fallback_seconds=90.0)
        is True
    )


def test_falls_back_to_idle_after_fallback_window_elapses():
    assert (
        should_show_spotify(is_playing=False, last_playing_at=100.0, now=191.0, fallback_seconds=90.0)
        is False
    )


def test_boundary_exactly_at_fallback_seconds_has_elapsed():
    assert (
        should_show_spotify(is_playing=False, last_playing_at=100.0, now=190.0, fallback_seconds=90.0)
        is False
    )
