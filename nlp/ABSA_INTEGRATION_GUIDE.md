# ABSA Integration Guide

This document describes the ABSA pipeline as a black box for the API and frontend teams. It specifies the input contract, the output schema, sample inputs and outputs, and recommended integration patterns. Operational instructions for running the pipeline locally are in `README_ABSA.md`.

## Pipeline contract

The pipeline is exposed as a single command-line program (`absa_run.py`) that consumes a CSV of reviews and produces a JSON report. The program is intended to be wrapped by the FastAPI backend rather than called directly from the frontend. A typical wrapping pattern is to enqueue an analysis job (analogous to the existing `/reviews/jobs` pattern in `main.py`), shell out to or import the pipeline, and serve the resulting JSON to the dashboard's Analysis tab.

The pipeline does not maintain state between runs. Every invocation reads a CSV, runs through six stages (load, English filter, sentence split, aspect match, BERTopic on residual, sentiment, aggregate), and writes a JSON file. There is no database dependency.

## Input contract

The input is a CSV file with the columns produced by the scraper in `main.py`. The pipeline reads `recommendationid`, `voted_up`, `review_text`, and `created_at`. Other columns are passed through without inspection. The `voted_up` field is preserved on each prediction record to support offline evaluation against Steam's binary recommendation, but it is not used as a training or aggregation signal.

Reviews shorter than 30 characters or that do not pass an English-language confidence threshold (langdetect, 0.85) are dropped before sentence splitting. Both thresholds are configurable in `absa_config.py`.

## Output schema

The output JSON has three top-level keys: `metadata`, `predefined_aspects`, and `discovered_topics`. The two aspect arrays use the same record shape so that the frontend can render them with one component, with `source` distinguishing the two cases and `discovered_topics` records carrying additional `keywords` and `cluster_id` fields.

A canonical aspect record contains the canonical aspect name, the source label, the total count of (sentence, aspect) pairs that contributed to the record, a sentiment block with raw counts and percentages alongside confidence-weighted percentages, the average model confidence across all predictions, a net score in the range [-1, 1] computed as the weighted positive percentage minus the weighted negative percentage divided by 100, and three example sentences per sentiment class drawn from the most confident predictions in that class.

The `metadata` block reports counts at every stage so that data loss can be traced (loaded → kept after English filter → sentences → matched pairs → discovered pairs), the model identifier in use, runtime in seconds, and a flag indicating whether BERTopic was skipped.

## Sample input

A scraped CSV from the existing scraper looks like this (one header row plus rows for each review). The `review_text` column may contain commas and is properly quoted by `csv.writer` in the scraper.

```
recommendationid,steamid,playtime_forever_minutes,voted_up,votes_up,review_text,created_at,language,steam_purchase
180123456,76561198000000001,4823,True,17,"The graphics are absolutely stunning, especially with ray tracing on. However the performance was a mess at launch with constant stutters. Story is incredible though, Johnny Silverhand steals every scene.",2024-01-15T12:00:00+00:00,english,True
180123457,76561198000000002,1290,False,4,"So many bugs. Crashes every hour. The Phantom Liberty DLC is great but base game performance is still rough on my old GPU.",2024-02-01T12:00:00+00:00,english,True
180123458,76561198000000003,8500,True,42,"Played the nomad lifepath and loved it. The open world is dense, side quests are far better than the main story honestly. Panam's questline is the best part of the whole game.",2024-03-10T12:00:00+00:00,english,True
180123459,76561198000000004,2100,True,9,"Driving controls feel terrible with keyboard. Combat is fun though, shooting feels weighty. The soundtrack is one of the best I've heard.",2024-04-22T12:00:00+00:00,english,True
180123460,76561198000000005,600,False,2,"Overpriced for what you get. Glitches everywhere, NPCs phasing through walls, T-posing pedestrians. Not worth it at full price.",2024-05-05T12:00:00+00:00,english,True
```

Real production input will be hundreds to tens of thousands of rows. The pipeline has been written with batched inference and lazy spaCy/BERTopic loading to handle this volume.

## Sample output

The output for the sample CSV above (or for `--sample` mode) is shaped as follows. The actual numbers will vary slightly between runs because BERTopic's UMAP step is stochastic; clustering output is therefore not bit-exact reproducible across runs, although the predefined-aspect output is fully deterministic.

```json
{
  "metadata": {
    "app_id": 1091500,
    "game_name": "Cyberpunk 2077",
    "model": "yangheng/deberta-v3-base-absa-v1.1",
    "reviews_loaded": 5,
    "reviews_kept_after_english_filter": 5,
    "reviews_dropped_non_english_or_short": 0,
    "sentences_analyzed": 13,
    "predefined_pairs": 18,
    "discovered_pairs": 0,
    "discovered_topic_count": 0,
    "runtime_seconds": 14.7,
    "bertopic_skipped": false
  },
  "predefined_aspects": [
    {
      "aspect": "performance",
      "source": "predefined",
      "mention_count": 3,
      "sentiment": {
        "positive": {"count": 0, "pct": 0.0,  "weighted_pct": 0.0},
        "neutral":  {"count": 0, "pct": 0.0,  "weighted_pct": 0.0},
        "negative": {"count": 3, "pct": 100.0,"weighted_pct": 100.0}
      },
      "average_confidence": 0.92,
      "net_score": -1.0,
      "examples": {
        "positive": [],
        "neutral": [],
        "negative": [
          "However the performance was a mess at launch with constant stutters.",
          "The Phantom Liberty DLC is great but base game performance is still rough on my old GPU.",
          "Crashes every hour."
        ]
      }
    },
    {
      "aspect": "graphics",
      "source": "predefined",
      "mention_count": 2,
      "sentiment": {
        "positive": {"count": 2, "pct": 100.0, "weighted_pct": 100.0},
        "neutral":  {"count": 0, "pct": 0.0,   "weighted_pct": 0.0},
        "negative": {"count": 0, "pct": 0.0,   "weighted_pct": 0.0}
      },
      "average_confidence": 0.94,
      "net_score": 1.0,
      "examples": {
        "positive": [
          "The graphics are absolutely stunning, especially with ray tracing on.",
          "The open world is dense, side quests are far better than the main story honestly."
        ],
        "neutral": [],
        "negative": []
      }
    },
    {
      "aspect": "johnny silverhand",
      "source": "predefined",
      "mention_count": 1,
      "sentiment": {
        "positive": {"count": 1, "pct": 100.0, "weighted_pct": 100.0},
        "neutral":  {"count": 0, "pct": 0.0,   "weighted_pct": 0.0},
        "negative": {"count": 0, "pct": 0.0,   "weighted_pct": 0.0}
      },
      "average_confidence": 0.91,
      "net_score": 1.0,
      "examples": {
        "positive": ["Story is incredible though, Johnny Silverhand steals every scene."],
        "neutral": [],
        "negative": []
      }
    }
  ],
  "discovered_topics": []
}
```

In a real run with thousands of reviews, `discovered_topics` will contain entries shaped like the example below. The `keywords` field is the c-TF-IDF top terms for that BERTopic cluster, the `cluster_id` is the integer label from the underlying HDBSCAN output, and the `aspect` field is the top keyword (or the top two keywords joined when the top keyword is ambiguous between clusters).

```json
{
  "aspect": "police",
  "source": "bertopic",
  "cluster_id": 7,
  "keywords": ["police", "ncpd", "wanted", "stars", "spawn"],
  "mention_count": 84,
  "sentiment": {
    "positive": {"count": 6,  "pct": 7.1,  "weighted_pct": 6.8},
    "neutral":  {"count": 12, "pct": 14.3, "weighted_pct": 13.1},
    "negative": {"count": 66, "pct": 78.6, "weighted_pct": 80.1}
  },
  "average_confidence": 0.86,
  "net_score": -0.733,
  "examples": {
    "positive": ["The police AI got a lot better after the 2.0 patch."],
    "neutral": ["The NCPD will spawn behind you if you commit a crime."],
    "negative": [
      "Police literally spawn out of thin air right next to you, ridiculous.",
      "NCPD AI is the worst part of this game, no chase, no cars, just teleporting cops."
    ]
  }
}
```

This example illustrates exactly the kind of emergent feedback that motivated including BERTopic in the pipeline: the police system was a measurable Cyberpunk 2077 launch issue that no curated game-aspect taxonomy would have flagged in advance.

## Field reference

The `mention_count` field is the count of distinct (sentence, aspect) pairs, not the count of unique reviews. A single review that mentions an aspect across three sentences contributes three to this count.

The `pct` and `weighted_pct` fields differ in how they aggregate. The unweighted percentage treats every prediction as equal, regardless of confidence. The weighted percentage sums the confidence values for each class and normalizes by the total summed confidence, which means high-confidence predictions count more and low-confidence predictions count less. The frontend should generally use `weighted_pct` for visual breakdowns since it produces more stable summaries when the model is uncertain on borderline cases. The `pct` field is exposed primarily for diagnostic comparison.

The `net_score` field is in the range [-1, 1] and is intended as a single-number summary suitable for sorting aspects from most-loved to most-hated in the dashboard. A value near zero can mean either uniformly neutral discussion or a balanced mix of positive and negative discussion; consult the full sentiment block to disambiguate.

The `examples` field carries up to three sentences per sentiment class, selected as the highest-confidence predictions in each class. These are intended for display in expandable sections of the dashboard and are not necessarily representative of the statistical distribution.

## Recommended integration pattern

The most natural extension of the existing FastAPI backend is to add a new asynchronous job type alongside the existing `/reviews/jobs` endpoints. A `POST /analysis/jobs` endpoint would accept an App ID and an optional date range, kick off the scrape if needed, then invoke the ABSA pipeline against the resulting CSV (or against an in-memory list of reviews, which is supported by the pipeline's internal functions if `absa_run.py` is bypassed). The result JSON can then be cached against the App ID and date range so that subsequent dashboard loads are immediate.

For the frontend, the `discovered_topics` array should be rendered in a section visually distinct from `predefined_aspects`, since the two carry different reliability characteristics. Predefined aspects always have a clear human-readable name; discovered topics carry a `keywords` array that the frontend can render as a small tag cluster to give users context for the otherwise terse `aspect` label.

## Determinism and caching

Predefined-aspect output is fully deterministic given a fixed input CSV: the same reviews will always produce the same predefined aspect records. Discovered topics are not deterministic because BERTopic's UMAP step is stochastic. If reproducible discovered-topic output is required, the seed can be set in `absa_topics.py` by passing `umap_model=UMAP(random_state=42)` to the BERTopic constructor; this is not done by default to keep the dependency surface minimal.

Cache invalidation should key on the App ID, the date range filter, and the pipeline version. Bumping a version constant in `absa_config.py` whenever the taxonomy or thresholds change is sufficient.

## Performance expectations

The dominant cost is the DeBERTa inference, which runs at roughly 10 to 12 (sentence, aspect) pairs per second on CPU. A typical Steam review of moderate length yields three to six sentences and three to six matched aspect pairs, so a thousand reviews translates to roughly 3,000 to 6,000 inference pairs and five to ten minutes of runtime on CPU. GPU acceleration (any consumer NVIDIA card) reduces this by roughly an order of magnitude. BERTopic adds a fixed embedding cost (a few seconds per thousand sentences) plus a clustering cost that scales sub-linearly.

The pipeline is intentionally batch-oriented and will need to be wrapped in a job queue rather than called synchronously from a request handler.
