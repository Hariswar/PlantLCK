# ABSA Section: Operation Guide

This document covers installation and day-to-day operation of the ABSA pipeline. For details on the JSON output and how to consume it from the API layer, see `ABSA_INTEGRATION_GUIDE.md`.

## What this section does

The pipeline takes a CSV of Steam reviews produced by the project's scraper and produces a JSON report containing per-aspect sentiment summaries. Two kinds of aspects are reported in parallel: predefined aspects from a curated taxonomy (graphics, performance, bugs, story, downloadable content, and so on, plus per-game overlays such as the Cyberpunk 2077 lifepaths and named characters), and emergent topics discovered by BERTopic on the sentences that did not match any predefined aspect.

## Files

The pipeline is split into four Python modules. `absa_config.py` holds the aspect taxonomy, the per-game overlays, model identifiers, and tunable thresholds. `absa_pipeline.py` contains the linear data flow from CSV load through preprocessing, English filtering, sentence splitting, aspect matching, sentiment classification, and aggregation. `absa_topics.py` is the BERTopic stage and is imported lazily so users who pass `--skip-bertopic` do not need its dependency cluster installed. `absa_run.py` is the command-line entry point that wires the stages together and writes the final JSON report.

## Installation

Create a fresh virtual environment and install the dependencies pinned in `requirements_absa.txt`. The pipeline has been written against Python 3.11 or 3.12. Python 3.14 may work but BERTopic's transitive dependencies (UMAP, HDBSCAN, numba) have historically lagged the newest Python releases. If you encounter installation failures, fall back to 3.12.

```
python -m pip install -r requirements_absa.txt
python -m spacy download en_core_web_sm
```

The first run will additionally download the DeBERTa ABSA model (~738 MB) and the sentence-transformers embedding model (~80 MB) from the HuggingFace Hub. Both are cached locally after the first download.

## Quick start

To verify the pipeline end-to-end without preparing a CSV, run the built-in sample mode:

```
python absa_run.py --sample --output sample_report.json
```

This processes a small handful of Cyberpunk 2077-flavored sample reviews and writes a JSON report. Inspect `sample_report.json` to confirm the schema and that the predefined and discovered sections are populated.

## Running on real data

Point the runner at a CSV produced by the FastAPI scraper and pass the Steam App ID so that game-specific aspects are merged into the taxonomy.

```
python absa_run.py --input reviews_1091500.csv --app-id 1091500 --output cp77_report.json
```

The CSV is expected to have the columns the scraper produces: `recommendationid`, `steamid`, `playtime_forever_minutes`, `voted_up`, `votes_up`, `review_text`, and optionally `created_at`, `language`, and `steam_purchase`.

## Command-line flags

`--input <path>` selects a CSV file. Mutually exclusive with `--sample`.

`--sample` uses the built-in sample reviews instead of a CSV.

`--app-id <int>` selects which game-specific aspect overlay to merge. Defaults to 1091500 (Cyberpunk 2077). If the App ID has no overlay defined in `absa_config.py`, only the base taxonomy is used.

`--output <path>` chooses the destination for the JSON report. Defaults to `absa_report.json`.

`--skip-bertopic` runs only the predefined-aspect path. Useful for fast iteration on the taxonomy without paying the embedding and clustering cost.

## Tuning

The most useful knobs for early testing live at the top of `absa_config.py`. `MIN_TOPIC_SIZE` controls how aggressively BERTopic suppresses small clusters; raise it to filter out joke clusters and meme repetitions, lower it to surface niche themes. `MIN_SENTENCE_TOKENS` and `MAX_SENTENCE_TOKENS` discard sentence fragments and run-ons. `ENGLISH_LANGDETECT_THRESHOLD` controls how strict the language filter is.

The aspect taxonomy itself is the other primary editing surface. Adding a new aspect requires only a new entry in `BASE_ASPECTS` (or in the per-game overlay) with its surface forms. Single-word forms are matched via spaCy lemmatization, so adding `"glitch"` automatically catches `"glitches"` and `"glitching"`. Multi-word forms are matched by lowercase substring on the original sentence text.

## Known limitations

Substring matching for multi-word phrases is case-insensitive but order-sensitive, so `"art style"` matches `"art style"` but not `"style of the art"`. The English language filter uses langdetect, which is generally reliable but can misclassify very short reviews; sentences shorter than `MIN_SENTENCE_TOKENS` are dropped before classification, which mitigates this. The predefined aspect matcher does not yet handle negation scoping (it relies entirely on DeBERTa's Local Context Focus layer for that), so a sentence like "the graphics are fine but the performance is awful" will register one positive prediction for graphics and one negative prediction for performance, which is the intended behavior.

## Files to upload to GitHub

Commit `absa_config.py`, `absa_pipeline.py`, `absa_topics.py`, `absa_run.py`, `requirements_absa.txt`, `README_ABSA.md`, and `ABSA_INTEGRATION_GUIDE.md`. Do not commit generated reports, downloaded model caches, or the `absa-finetuned/` directory if it exists from earlier experiments.
