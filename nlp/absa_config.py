"""
ABSA Pipeline Configuration
============================
All knobs and taxonomies for the ABSA pipeline live here. Edit this file
to change models, add aspects, expand synonym lists, or tune thresholds
without touching the pipeline code.
"""

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
SENTIMENT_MODEL = "yangheng/deberta-v3-base-absa-v1.1"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SPACY_MODEL = "en_core_web_sm"

# ---------------------------------------------------------------------------
# Preprocessing thresholds
# ---------------------------------------------------------------------------
MIN_REVIEW_CHARS = 30           # Drop reviews shorter than this
MIN_SENTENCE_TOKENS = 4         # Drop sentence fragments
MAX_SENTENCE_TOKENS = 80        # Drop run-on sentences (usually copy-paste noise)
ENGLISH_LANGDETECT_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# BERTopic
# ---------------------------------------------------------------------------
# Set MIN_TOPIC_SIZE high enough to suppress small in-jokes and meme
# clusters but low enough that legitimate emergent themes (e.g., a
# specific NPC, a specific patch issue) still surface. 15 is a starting
# point; tune once real review volumes are in hand.
MIN_TOPIC_SIZE = 15
TOP_KEYWORDS_PER_TOPIC = 5

# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
EXAMPLES_PER_SENTIMENT = 3      # How many sample sentences to keep per class

# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
SENTIMENT_BATCH_SIZE = 16

# ---------------------------------------------------------------------------
# Base aspect taxonomy
# ---------------------------------------------------------------------------
# Each entry maps a canonical aspect name to a list of surface forms.
# Single-token forms are matched via spaCy lemmatization (so "glitches"
# matches "glitch"). Multi-token forms are matched by lowercase substring.
#
# Keep surface forms unambiguous in everyday English. Avoid short or
# common words that produce false positives (for example, do not add
# "rt" as a synonym for ray tracing because it overlaps with retweets
# and other unrelated text).
BASE_ASPECTS = {
    "graphics": [
        "graphics", "graphic", "visuals", "visual", "art", "art style",
        "art direction", "texture", "lighting", "model", "animation",
        "shader", "render", "ray tracing",
    ],
    "performance": [
        "performance", "framerate", "frame rate", "fps", "optimization",
        "optimized", "optimisation", "lag", "stutter", "smooth",
        "frame drop", "frame drops",
    ],
    "gameplay": [
        "gameplay", "mechanic", "mechanics", "combat", "shooting",
        "mission", "quest", "gameplay loop", "core loop",
    ],
    "story": [
        "story", "narrative", "plot", "writing", "dialogue", "ending",
        "lore", "storyline", "side story", "main story",
    ],
    "characters": [
        "character", "characters", "cast", "protagonist", "antagonist",
        "npc", "npcs",
    ],
    "controls": [
        "controls", "control", "aiming", "movement", "driving",
        "controller", "keybind", "keybinds", "input",
    ],
    "audio": [
        "audio", "sound", "music", "soundtrack", "voice acting",
        "sfx", "score", "ost",
    ],
    "difficulty": [
        "difficulty", "difficult", "hard", "easy", "challenging",
        "grind", "grinding", "balanced", "punishing",
    ],
    "bugs": [
        "bug", "bugs", "buggy", "glitch", "glitches", "crash",
        "crashes", "freezing", "broken", "softlock", "hardlock",
    ],
    "multiplayer": [
        "multiplayer", "pvp", "pve", "online", "co-op", "coop",
        "matchmaking", "lobby", "server",
    ],
    "content": [
        "side quest", "side content", "endgame", "replay",
        "replayability", "length", "playtime", "open world",
    ],
    "price": [
        "price", "pricing", "value", "cost", "expensive", "cheap",
        "worth", "overpriced",
    ],
    "dlc": [
        "dlc", "downloadable content", "expansion", "expansions",
        "season pass", "addon", "add-on", "post-launch content",
        "post launch content",
    ],
}

# ---------------------------------------------------------------------------
# Game-specific aspect overlays
# ---------------------------------------------------------------------------
# Indexed by Steam App ID. These are merged with BASE_ASPECTS at runtime
# when the user passes --app-id. The overlay covers entities that are
# noteworthy enough to track natively rather than waiting for BERTopic
# to discover them.
#
# Naming guideline: prefer canonical names with spaces over slugs, since
# the canonical name is what appears in dashboard labels.
GAME_SPECIFIC_ASPECTS = {
    # Cyberpunk 2077
    1091500: {
        # Lifepaths (the three opening routes)
        "nomad lifepath": ["nomad", "nomad lifepath"],
        "streetkid lifepath": ["street kid", "streetkid", "street kid lifepath"],
        "corpo lifepath": ["corpo", "corpo lifepath"],
        # Major characters that are unambiguous in plain text
        "johnny silverhand": ["johnny", "silverhand", "johnny silverhand"],
        "panam": ["panam"],
        "judy": ["judy"],
        "jackie": ["jackie"],
        "takemura": ["takemura", "goro takemura"],
        # Phantom Liberty DLC and its principals
        "phantom liberty": ["phantom liberty"],
        "songbird": ["songbird"],
        "solomon reed": ["solomon reed", "reed"],
        "dogtown": ["dogtown"],
    },
}

# Display names for app IDs the pipeline knows about. Used only for
# the metadata block in the output JSON; not load-bearing.
GAME_NAMES = {
    1091500: "Cyberpunk 2077",
}


def aspects_for_app(app_id: int | None) -> dict[str, list[str]]:
    """
    Return the merged aspect dictionary for a given Steam App ID.

    If app_id is None or has no overlay, the base taxonomy is returned
    unchanged. If an overlay exists, its entries are added on top of
    the base. Overlay entries do not replace base entries.
    """
    merged = {name: list(syns) for name, syns in BASE_ASPECTS.items()}
    if app_id is not None and app_id in GAME_SPECIFIC_ASPECTS:
        for name, syns in GAME_SPECIFIC_ASPECTS[app_id].items():
            merged[name] = list(syns)
    return merged
