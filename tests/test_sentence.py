import re
from dataclasses import replace
from datetime import datetime

from tinyscreen.sentence import (
    ARTIST_POOLS,
    DESCRIPTOR_POOLS,
    DUTCH_WORDS,
    WIND_TIER_50_PLUS,
    WIND_TIERS,
    _day_category,
    _night_artist,
    generate_sentence,
    is_night,
    pick_dutch_word,
    pick_wind_sentence,
    time_of_day_bucket,
)
from tinyscreen.weather import MockWeatherClient


class FakeRng:
    """A stand-in for random.Random with fully deterministic output, so
    category-selection tests don't depend on randomness landing a certain
    way."""

    def __init__(self, random_value: float = 0.9, choice_index: int = 0):
        self._random_value = random_value
        self._choice_index = choice_index

    def random(self) -> float:
        return self._random_value

    def choice(self, seq):
        return seq[self._choice_index]


def weather(**overrides):
    base = MockWeatherClient().fetch()
    return replace(base, **overrides)


# --- priority order -----------------------------------------------------


def test_snow_takes_priority_over_temp_and_clouds():
    w = weather(weather_main="Snow", temp=25.0, clouds_pct=0)
    assert _day_category(w, FakeRng()) == "snow"


def test_foggy_takes_priority_over_changeable_and_temp():
    w = weather(weather_main="Fog", temp=25.0, clouds_pct=50)
    assert _day_category(w, FakeRng()) == "foggy"


def test_changeable_is_partly_but_not_fully_clouded():
    changeable = weather(weather_main="Clouds", clouds_pct=50, temp=15.0)
    assert _day_category(changeable, FakeRng()) == "changeable"

    barely_clouded = weather(weather_main="Clouds", clouds_pct=10, temp=15.0)
    assert _day_category(barely_clouded, FakeRng()) != "changeable"


def test_graphic_clear_only_triggers_on_clear_days_within_its_odds():
    clear = weather(weather_main="Clear", temp=15.0)
    assert _day_category(clear, FakeRng(random_value=0.1)) == "graphic_clear"
    assert _day_category(clear, FakeRng(random_value=0.9)) == "mild_clear"

    # Even a low roll shouldn't force graphic_clear on a non-clear day.
    rainy = weather(weather_main="Rain", temp=15.0)
    assert _day_category(rainy, FakeRng(random_value=0.1)) != "graphic_clear"


def test_temp_brackets_for_clear_days():
    rng = FakeRng(random_value=0.9)  # stay above the graphic_clear threshold
    assert _day_category(weather(weather_main="Clear", temp=5.0), rng) == "cold_clear"
    assert _day_category(weather(weather_main="Clear", temp=15.0), rng) == "mild_clear"
    assert _day_category(weather(weather_main="Clear", temp=25.0), rng) == "hot_sunny"


def test_temp_brackets_for_wet_or_grey_days():
    rng = FakeRng()
    assert _day_category(weather(weather_main="Rain", temp=5.0), rng) == "cold_wet"
    assert _day_category(weather(weather_main="Rain", temp=15.0), rng) == "mild_wet"
    assert _day_category(weather(weather_main="Rain", temp=25.0), rng) == "hot_humid"


# --- night sub-pick -------------------------------------------------------


def test_night_artist_by_sky_condition():
    assert _night_artist(weather(weather_main="Fog"), FakeRng()) == "Whistler"
    assert _night_artist(weather(weather_main="Clear"), FakeRng()) == "Van Gogh"
    assert _night_artist(weather(weather_main="Rain"), FakeRng()) == "Hopper"
    assert _night_artist(weather(weather_main="Clouds"), FakeRng()) == "Hopper"


def test_is_night_boundaries():
    assert is_night(datetime(2026, 1, 1, 21, 59)) is False
    assert is_night(datetime(2026, 1, 1, 22, 0)) is True
    assert is_night(datetime(2026, 1, 1, 4, 59)) is True
    assert is_night(datetime(2026, 1, 1, 5, 0)) is False


# --- time of day buckets ---------------------------------------------------


def test_time_of_day_bucket_boundaries():
    assert time_of_day_bucket(datetime(2026, 1, 1, 5, 0)) == "morning"
    assert time_of_day_bucket(datetime(2026, 1, 1, 11, 59)) == "morning"
    assert time_of_day_bucket(datetime(2026, 1, 1, 12, 0)) == "afternoon"
    assert time_of_day_bucket(datetime(2026, 1, 1, 17, 59)) == "afternoon"
    assert time_of_day_bucket(datetime(2026, 1, 1, 18, 0)) == "evening"
    assert time_of_day_bucket(datetime(2026, 1, 1, 21, 59)) == "evening"
    assert time_of_day_bucket(datetime(2026, 1, 1, 22, 0)) == "night"
    assert time_of_day_bucket(datetime(2026, 1, 1, 4, 59)) == "night"


# --- wind sentences ---------------------------------------------------------


def test_pick_wind_sentence_tiers():
    rng = FakeRng(choice_index=0)
    assert pick_wind_sentence(5.0, rng) == WIND_TIERS[0][1][0]
    assert pick_wind_sentence(15.0, rng) == WIND_TIERS[1][1][0]
    assert pick_wind_sentence(65.0, rng) == WIND_TIER_50_PLUS[0]


def test_pick_wind_sentence_tier_boundaries_are_exclusive_upper():
    rng = FakeRng(choice_index=0)
    assert pick_wind_sentence(9.99, rng) == WIND_TIERS[0][1][0]
    assert pick_wind_sentence(10.0, rng) == WIND_TIERS[1][1][0]


# --- dutch word rotation ----------------------------------------------------


def test_pick_dutch_word_rotates_by_day_of_year():
    day1 = datetime(2026, 1, 1)  # tm_yday == 1
    day2 = datetime(2026, 1, 2)  # tm_yday == 2
    assert pick_dutch_word(day1) == DUTCH_WORDS[1 % len(DUTCH_WORDS)]
    assert pick_dutch_word(day2) == DUTCH_WORDS[2 % len(DUTCH_WORDS)]


# --- full sentence assembly -------------------------------------------------


def test_generate_sentence_matches_template_shape():
    w = weather(weather_main="Clear", temp=18.0, wind_speed_kmh=12.0)
    now = datetime(2026, 7, 25, 15, 7)  # afternoon

    generated = generate_sentence(w, now, rng=FakeRng(random_value=0.9))

    assert re.match(r"^It is currently \d+° and a \w+ afternoon in AMS\. ", generated.text)
    assert "Feels like a" in generated.text and "painting." in generated.text
    assert "Dutch word of the day:" in generated.text
    assert generated.text.endswith(".")
    assert generated.category == "mild_clear"


def test_generate_sentence_uses_night_artist_after_dark():
    w = weather(weather_main="Clear", temp=5.0)
    night = datetime(2026, 7, 25, 23, 0)

    generated = generate_sentence(w, night, rng=FakeRng(random_value=0.9))

    assert "Feels like a Van Gogh painting" in generated.text
    # descriptor still comes from the matching day category (cold_clear),
    # not invented night-only wording - and the category returned for color
    # purposes reflects that too.
    assert generated.category == "cold_clear"
    assert any(word in generated.text for word in DESCRIPTOR_POOLS["cold_clear"])


def test_every_pool_has_multiple_options_except_snow():
    for category, artists in ARTIST_POOLS.items():
        if category == "snow":
            continue
        assert len(artists) >= 3, f"{category} should have 3-4 artists for variety"
