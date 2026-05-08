"""
ABSA Run
=========
Command-line entry point for the ABSA pipeline.

Usage examples
--------------
Run on a real CSV scraped by the FastAPI backend:

    python absa_run.py --input reviews.csv --app-id 1091500 --output report.json

Run with a small built-in sample (no CSV required, useful for first-run
verification on a fresh checkout):

    python absa_run.py --sample --output sample_report.json

Skip the BERTopic stage to iterate faster on the predefined-aspect path:

    python absa_run.py --input reviews.csv --skip-bertopic --output report.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from absa_config import GAME_NAMES, SENTIMENT_MODEL, aspects_for_app
from absa_pipeline import (
    aggregate,
    filter_english,
    load_reviews,
    load_sentiment_classifier,
    match_aspects,
    residual_sentences,
    run_sentiment,
    split_to_sentences,
)


# A small built-in sample so the pipeline can be exercised without a CSV.
# Mirrors the scraper's CSV column names.
_SAMPLE_REVIEWS = [
    {
        "recommendationid": "1",
        "voted_up": "True",
        "review_text": (
            "The graphics are absolutely stunning, especially with ray tracing on. "
            "However the performance was a mess at launch with constant stutters. "
            "Story is incredible though, Johnny Silverhand steals every scene."
        ),
        "created_at": "2024-01-15T12:00:00+00:00",
    },
    {
        "recommendationid": "2",
        "voted_up": "False",
        "review_text": (
            "So many bugs. Crashes every hour. The Phantom Liberty DLC is great "
            "but base game performance is still rough on my old GPU."
        ),
        "created_at": "2024-02-01T12:00:00+00:00",
    },
    {
        "recommendationid": "3",
        "voted_up": "True",
        "review_text": (
            "Played the nomad lifepath and loved it. The open world is dense, "
            "side quests are far better than the main story honestly. "
            "Panam's questline is the best part of the whole game."
        ),
        "created_at": "2024-03-10T12:00:00+00:00",
    },
    {
        "recommendationid": "4",
        "voted_up": "True",
        "review_text": (
            "Driving controls feel terrible with keyboard. Combat is fun though, "
            "shooting feels weighty. The soundtrack is one of the best I've heard."
        ),
        "created_at": "2024-04-22T12:00:00+00:00",
    },
    {
        "recommendationid": "5",
        "voted_up": "False",
        "review_text": (
            "Overpriced for what you get. Glitches everywhere, NPCs phasing through "
            "walls, T-posing pedestrians. Not worth it at full price."
        ),
        "created_at": "2024-05-05T12:00:00+00:00",
    },
]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ABSA pipeline runner")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="Path to reviews CSV from the scraper")
    src.add_argument("--sample", action="store_true", help="Use built-in sample reviews")
    parser.add_argument(
        "--app-id",
        type=int,
        default=1091500,
        help="Steam App ID (used to merge game-specific aspects). Default: Cyberpunk 2077",
    )
    parser.add_argument(
        "--output",
        default="absa_report.json",
        help="Path to write the JSON report",
    )
    parser.add_argument(
        "--skip-bertopic",
        action="store_true",
        help="Skip topic discovery (predefined aspects only)",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    overall_t0 = time.time()

    # ---- Load
    if args.sample:
        print("Using built-in sample reviews.")
        reviews = list(_SAMPLE_REVIEWS)
    else:
        print(f"Loading reviews from: {args.input}")
        reviews = load_reviews(args.input)
    print(f"  {len(reviews)} reviews loaded.")

    # ---- English filter
    reviews_kept, dropped = filter_english(reviews)
    print(f"English filter: kept {len(reviews_kept)}, dropped {dropped}.")

    # ---- Sentence splitting
    print("Splitting into sentences...")
    sentences = split_to_sentences(reviews_kept)
    print(f"  {len(sentences)} sentences.")

    # ---- Aspect matching
    aspects = aspects_for_app(args.app_id)
    print(f"Matching against {len(aspects)} aspects...")
    matched = match_aspects(sentences, aspects)
    print(f"  {len(matched)} (sentence, aspect) pairs from predefined aspects.")

    # ---- BERTopic on residual
    discovered_pairs: list = []
    cluster_metadata: dict = {}
    if not args.skip_bertopic:
        residual = residual_sentences(sentences, matched)
        from absa_topics import discover_topics
        discovered_pairs, cluster_metadata = discover_topics(residual)

    # ---- Sentiment
    classifier = load_sentiment_classifier(SENTIMENT_MODEL)
    matched_enriched = run_sentiment(matched, classifier)
    discovered_enriched = run_sentiment(discovered_pairs, classifier) if discovered_pairs else []

    # ---- Aggregation
    predefined_summary = aggregate(matched_enriched, source_label="predefined")
    discovered_summary = aggregate(
        discovered_enriched,
        source_label="bertopic",
        extra_fields=cluster_metadata,
    )

    # ---- Assemble final report
    report = {
        "metadata": {
            "app_id": args.app_id,
            "game_name": GAME_NAMES.get(args.app_id, "Unknown"),
            "model": SENTIMENT_MODEL,
            "reviews_loaded": len(reviews),
            "reviews_kept_after_english_filter": len(reviews_kept),
            "reviews_dropped_non_english_or_short": dropped,
            "sentences_analyzed": len(sentences),
            "predefined_pairs": len(matched_enriched),
            "discovered_pairs": len(discovered_enriched),
            "discovered_topic_count": len(cluster_metadata),
            "runtime_seconds": round(time.time() - overall_t0, 1),
            "bertopic_skipped": args.skip_bertopic,
        },
        "predefined_aspects": predefined_summary,
        "discovered_topics": discovered_summary,
    }

    # Drop the cached spaCy doc objects before serializing
    # (they were only needed during matching).
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to: {args.output}")
    print(f"Total runtime: {report['metadata']['runtime_seconds']}s")


if __name__ == "__main__":
    main()
