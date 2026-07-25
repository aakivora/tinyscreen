"""Generates the scrolling idle-mode sentence: weather -> mood -> artist,
plus a wind observation and a Dutch word of the day.

Content (category definitions, artist pools, wind sentences, Dutch word
list, and the master template) is transcribed from weather_artist_mapping.md
- this module intentionally doesn't invent new categories or wording beyond
what that file specifies. Where the file describes something conceptually
but doesn't map it onto a specific weather-API field (see the two "judgment
call" comments below), the choice is called out explicitly rather than
buried silently.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime

from tinyscreen.weather import WeatherReading

ARTIST_POOLS: dict[str, list[str]] = {
    "snow": ["Robert Ryman"],
    "cold_wet": ["Turner", "Friedrich", "Hopper", "Munch", "Rembrandt"],
    "cold_clear": ["Bruegel", "Monet", "Georgia O'Keeffe", "Agnes Martin"],
    "mild_wet": ["Monet", "Caillebotte", "Constable", "Hopper"],
    "mild_clear": ["Renoir", "Sisley", "Vermeer", "Agnes Martin", "Degas", "Josef Albers"],
    "hot_sunny": ["Van Gogh", "Matisse", "Hockney", "Sorolla", "Klimt"],
    "hot_humid": ["Rothko", "Munch", "Francis Bacon"],
    "foggy": ["Whistler", "Friedrich", "Monet", "Turner", "Richter"],
    "graphic_clear": ["Mondrian", "Sol LeWitt", "Yves Klein", "Frank Stella"],
    "changeable": ["Picasso", "Magritte", "Dali"],
}

DESCRIPTOR_POOLS: dict[str, list[str]] = {
    "cold_wet": ["bleak", "damp", "grey"],
    "cold_clear": ["crisp", "sharp", "still"],
    "snow": ["hushed", "white-out", "muffled"],
    "mild_wet": ["soft", "drizzly", "grey"],
    "mild_clear": ["mild", "easy", "pleasant"],
    "hot_sunny": ["golden", "sun-drenched", "bright"],
    "hot_humid": ["heavy", "thick", "close"],
    "foggy": ["misty", "hazy", "blurred"],
    "graphic_clear": ["sharp", "bold", "crisp"],
    "changeable": ["restless", "unsettled", "shifting"],
}

# (upper_bound_km/h exclusive, sentence pool). "0-10 km/h" etc. from the
# source file is read as [previous_upper, upper).
WIND_TIERS: list[tuple[float, list[str]]] = [
    (10, ["The wind is dead still.", "The wind is barely breathing.", "The wind is suspiciously calm."]),
    (20, ["The wind is a gentle breeze.", "The wind is mild, if a little disrespectful.", "The wind is manageable, for now."]),
    (30, ["The wind is hat-threatening.", "The wind is properly rude today.", "The wind is jacket-flapping."]),
    (40, ["The wind is bike-wobbling.", "The wind is actively hostile.", "The wind is umbrella-ending, no negotiation."]),
    (50, ["The wind is borderline violent.", "The wind is personally offensive today.", "The wind means it, hold on tight."]),
]
WIND_TIER_50_PLUS = [
    "The wind is apocalyptic, honestly.",
    "The wind is biblical. Don't bike today.",
    "The wind has opinions, and they are loud.",
]

DUTCH_WORDS: list[str] = [
    "gezellig", "lekker", "druk", "gedoe",
    "uitwaaien", "borrel", "polderen", "doei",
    "lekker weertje", "kou", "hallo", "dag",
    "alsjeblieft", "dankjewel", "sorry", "gefeliciteerd",
    "proost", "smakelijk", "gezondheid", "welterusten",
    "tot ziens", "doeg", "hoi", "schat",
    "lieverd", "maatje", "vriendje", "buurman",
    "buurvrouw", "huisje", "tuintje", "fietsje",
    "kopje", "biertje", "wijntje", "etentje",
    "avondje", "weekendje", "zonnetje", "regenbui",
    "onweer", "storm", "mist", "sneeuw",
    "hagel", "wolk", "regenboog", "zonsopgang",
    "zonsondergang", "maanlicht", "sterrenhemel", "ochtend",
    "middag", "avond", "nacht", "vandaag",
    "morgen", "gisteren", "overmorgen", "eergisteren",
    "weekend", "vakantie", "feestdag", "verjaardag",
    "bruiloft", "begrafenis", "kerstmis", "oud en nieuw",
    "koningsdag", "bevrijdingsdag", "sinterklaas", "pepernoot",
    "oliebol", "stroopwafel", "poffertjes", "bitterbal",
    "kroket", "haring", "drop", "pindakaas",
    "hagelslag", "vla", "appeltaart", "erwtensoep",
    "stamppot", "boerenkool", "hutspot", "frikandel",
    "patat", "mayonaise", "kaas", "melk",
    "boter", "brood", "beschuit", "ontbijt",
    "lunch", "diner", "maaltijd", "recept",
    "keuken", "pan", "bord", "vork",
    "mes", "lepel", "glas", "fles",
    "theepot", "koffiepot", "zetel", "bank",
    "tafel", "stoel", "raam", "deur",
    "trap", "zolder", "kelder", "tuin",
    "balkon", "straat", "stoep", "fietspad",
    "kanaal", "gracht", "brug", "molen",
    "kasteel", "kerk", "markt", "plein",
    "winkel", "supermarkt", "bakkerij", "slager",
    "apotheek", "ziekenhuis", "school", "universiteit",
    "bibliotheek", "museum", "theater", "bioscoop",
    "station", "trein", "tram", "bus",
    "metro", "fiets", "auto", "boot",
    "vliegtuig", "brommer", "step", "rijbewijs",
    "verkeer", "file", "opstopping", "wegwerkzaamheden",
    "parkeerplaats", "benzinestation", "snelweg", "sluiproute",
    "omleiding", "vertraging", "vroeg", "laat",
    "op tijd", "haast", "rustig", "druktemaker",
    "gezelligheid", "huiselijkheid", "knus", "behaaglijk",
    "warm", "koud", "fris", "benauwd",
    "drukkend", "zwoel", "kil", "guur",
    "buiig", "somber", "zonnig", "bewolkt",
    "helder", "donker", "licht", "schemer",
    "schemering", "tegenlicht", "blauw", "rood",
    "geel", "groen", "oranje", "paars",
    "roze", "bruin", "grijs", "zwart",
    "wit", "goud", "zilver", "glimlach",
    "lach", "grap", "grapjas", "mopje",
    "kwinkslag", "plagerij", "plaagstoot", "knipoog",
    "kriebel", "kietelen", "giechelen", "schaterlachen",
    "huilen", "verdriet", "blijdschap", "geluk",
    "liefde", "vriendschap", "verlangen", "heimwee",
    "nostalgie", "herinnering", "dromen", "hoop",
    "vertrouwen", "moed", "lef", "durf",
    "onzekerheid", "twijfel", "verwarring", "verbazing",
    "verrassing", "schrik", "angst", "opwinding",
    "enthousiasme", "nieuwsgierigheid", "verveling", "ongeduld",
    "geduld", "rust", "kalmte", "stilte",
    "lawaai", "herrie", "kabaal", "gedruis",
    "geroezemoes", "gebabbel", "kletspraat", "roddel",
    "nieuwtje", "verhaal", "sprookje", "gedicht",
    "lied", "liedje", "melodie", "ritme",
    "dans", "feest", "festiviteit", "gezelschap",
    "gezelschapsspel", "kaartspel", "bordspel", "puzzel",
    "raadsel", "woordspeling", "uitdrukking", "gezegde",
    "spreekwoord", "wijsheid", "inzicht", "kennis",
    "ervaring", "vaardigheid", "talent", "creativiteit",
    "inspiratie", "verbeelding", "fantasie", "avontuur",
    "ontdekking", "verkenning", "reis", "uitstapje",
    "wandeling", "fietstocht", "boottocht", "picknick",
    "strandje", "duin", "bos", "weiland",
    "akker", "korenveld", "tulp", "narcis",
    "klaproos", "madeliefje", "paardenbloem", "klaver",
    "eik", "berk", "wilg", "populier",
    "egel", "konijn", "eekhoorn", "mus",
    "merel", "meeuw", "eend", "zwaan",
    "ooievaar", "koe", "schaap", "geit",
    "paard", "kat", "hond", "puppy",
    "kitten", "visje", "goudvis", "aquarium",
    "dierentuin", "kinderboerderij", "speeltuin", "schommel",
    "glijbaan", "zandbak", "knikkers", "vlieger",
    "zeepbellen", "springtouw", "verstoppertje", "tikkertje",
    "verjaardagsfeestje", "cadeau", "kaartje", "ballon",
    "slinger", "taart", "kaarsje", "lied zingen",
    "toost", "gastvrijheid", "gastvrij", "gulheid",
    "vrijgevigheid", "vriendelijkheid", "beleefdheid", "eerlijkheid",
    "betrouwbaarheid",
]

GRAPHIC_CLEAR_CHANCE = 0.25  # "~1 in 4 clear days" per the source file

_FOGGY_MAIN = {"Mist", "Fog", "Haze", "Smoke"}
# "rain OR overcast/grey" (day categories) / "overcast OR humid/heavy"
# (hot_humid) are both read as one wet-or-grey axis: any OWM condition that
# isn't literally "Clear" and isn't otherwise categorized (snow/fog).
_WET_OR_GREY_MAIN = {"Rain", "Drizzle", "Thunderstorm", "Clouds"}


def is_night(now: datetime) -> bool:
    return now.hour >= 22 or now.hour < 5


def time_of_day_bucket(now: datetime) -> str:
    hour = now.hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "night"


def _day_category(weather: WeatherReading, rng: random.Random) -> str:
    """The non-night branch of the priority chain: snow -> foggy ->
    changeable -> (graphic_clear override | temp+wet/dry). Also used to pick
    a *descriptor* even when it's night, since the source file gives night
    its own artist sub-pick (see _night_artist) but no separate descriptor
    pool - see the judgment call in classify_category below.
    """
    if weather.weather_main == "Snow":
        return "snow"
    if weather.weather_main in _FOGGY_MAIN:
        return "foggy"
    # Judgment call: "changeable" is described as "partly cloudy with rain
    # chance, or conditions shifting within the day" - but the Current
    # Weather endpoint (the only one this project calls) has no forecast/
    # rain-probability field to detect "rain chance" with. Approximated as
    # partly-but-not-fully clouded (20-70% cover) as the closest available
    # proxy for "mixed/in-between," rather than guessing at unavailable data.
    if weather.weather_main == "Clouds" and 20 <= weather.clouds_pct <= 70:
        return "changeable"

    temp = weather.temp
    if weather.weather_main == "Clear":
        if rng.random() < GRAPHIC_CLEAR_CHANCE:
            return "graphic_clear"
        if temp < 10:
            return "cold_clear"
        if temp < 20:
            return "mild_clear"
        return "hot_sunny"

    # Not clear and not otherwise categorized above: the wet/overcast branch.
    if temp < 10:
        return "cold_wet"
    if temp < 20:
        return "mild_wet"
    return "hot_humid"


def _night_artist(weather: WeatherReading, rng: random.Random) -> str:
    """Night's 3-way sub-pick (clear/urban-quiet/misty-foggy) doesn't map
    directly onto OWM fields for the "urban/quiet" case - it's a mood, not a
    condition. Read as the default: any night that isn't clearly clear or
    foggy (cloudy, rainy, snowy, changeable) falls back to it.
    """
    if weather.weather_main in _FOGGY_MAIN:
        return "Whistler"
    if weather.weather_main == "Clear":
        return "Van Gogh"
    return "Hopper"


def pick_artist(category: str, rng: random.Random) -> str:
    return rng.choice(ARTIST_POOLS[category])


def pick_descriptor(category: str, rng: random.Random) -> str:
    return rng.choice(DESCRIPTOR_POOLS[category])


def pick_wind_sentence(wind_speed_kmh: float, rng: random.Random) -> str:
    for upper_bound, sentences in WIND_TIERS:
        if wind_speed_kmh < upper_bound:
            return rng.choice(sentences)
    return rng.choice(WIND_TIER_50_PLUS)


def pick_dutch_word(now: datetime) -> str:
    """Rotates by day-of-year modulo list length, per the source file
    ("no reliable free API exists for this")."""
    index = now.timetuple().tm_yday % len(DUTCH_WORDS)
    return DUTCH_WORDS[index]


@dataclass
class GeneratedSentence:
    text: str
    category: str  # one of the 10 keys in ARTIST_POOLS/DESCRIPTOR_POOLS/CATEGORY_COLORS -
    # used by the renderer to pick a text color matching the weather mood.


def generate_sentence(
    weather: WeatherReading, now: datetime, rng: random.Random | None = None
) -> GeneratedSentence:
    rng = rng or random.Random()

    # Judgment call: the source file's priority order puts "Night" ahead of
    # snow/foggy/changeable for the *artist* pick, but has no night-specific
    # descriptor pool. Rather than inventing new descriptor words (which the
    # brief explicitly says not to do), the descriptor always comes from the
    # underlying snow/foggy/changeable/graphic_clear/temp+wet-dry category,
    # and only the artist swaps to the night sub-pick after sunset/before
    # sunrise - so a clear winter night reads as "10° and crisp night in
    # AMS. Feels like a Van Gogh painting," borrowing "crisp" from
    # cold_clear rather than leaving it blank.
    category = _day_category(weather, rng)
    artist = _night_artist(weather, rng) if is_night(now) else pick_artist(category, rng)
    descriptor = pick_descriptor(category, rng)
    wind_sentence = pick_wind_sentence(weather.wind_speed_kmh, rng)
    dutch_word = pick_dutch_word(now)
    time_bucket = time_of_day_bucket(now)

    text = (
        f"It is currently {round(weather.temp)}° and a {descriptor} {time_bucket} in AMS. "
        f"Feels like a {artist} painting. "
        f"{wind_sentence} Dutch word of the day: {dutch_word}."
    )
    return GeneratedSentence(text=text, category=category)
