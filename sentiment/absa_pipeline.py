"""
ABSA Pipeline
==============
Linear flow from raw scraped reviews to a per-aspect sentiment summary.

Stages:
    1. load_reviews          : Read the scraper CSV into dicts
    2. filter_english        : Defensive filter for non-English reviews
    3. split_to_sentences    : spaCy-based sentence splitting
    4. match_aspects         : Lemmatized matching against the taxonomy
    5. run_sentiment         : DeBERTa ABSA on each (sentence, aspect) pair
    6. aggregate             : Per-aspect rollup with confidence weighting

This module deliberately keeps each stage as a plain function so the
caller (absa_run.py) can compose them, swap them, or skip them during
testing.
"""

from __future__ import annotations

import csv
import time
from collections import defaultdict
from typing import Any, Iterable

import spacy
from langdetect import detect_langs, DetectorFactory, LangDetectException
from transformers import pipeline

from absa_config import (
    SENTIMENT_MODEL,
    SPACY_MODEL,
    MIN_REVIEW_CHARS,
    MIN_SENTENCE_TOKENS,
    MAX_SENTENCE_TOKENS,
    ENGLISH_LANGDETECT_THRESHOLD,
    EXAMPLES_PER_SENTIMENT,
    SENTIMENT_BATCH_SIZE,
)

# Make langdetect deterministic across runs.
DetectorFactory.seed = 0

# ---------------------------------------------------------------------------
# Lazy spaCy loader
# ---------------------------------------------------------------------------
_NLP = None


def _get_nlp():
    """Load spaCy once and cache it."""
    global _NLP
    if _NLP is None:
        try:
            _NLP = spacy.load(SPACY_MODEL, disable=["ner", "parser"])
            # We need the sentencizer because parser is disabled for speed.
            _NLP.add_pipe("sentencizer")
        except OSError as exc:
            raise RuntimeError(
                f"spaCy model '{SPACY_MODEL}' is not installed. "
                f"Install it with: python -m spacy download {SPACY_MODEL}"
            ) from exc
    return _NLP


# ---------------------------------------------------------------------------
# Stage 1: Load
# ---------------------------------------------------------------------------
def load_reviews(csv_path: str) -> list[dict[str, Any]]:
    """
    Load reviews from a CSV produced by the FastAPI scraper.

    Expected columns: recommendationid, steamid, playtime_forever_minutes,
    voted_up, votes_up, review_text. Additional columns are passed through.
    """
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


# ---------------------------------------------------------------------------
# Stage 2: English filter
# ---------------------------------------------------------------------------
def is_probably_english(text: str) -> bool:
    """
    Defensive check that catches reviews that slipped past the scraper's
    language=english flag. Uses langdetect with a confidence threshold.
    """
    if not text or len(text) < 10:
        return False
    try:
        candidates = detect_langs(text)
    except LangDetectException:
        return False
    for candidate in candidates:
        if candidate.lang == "en" and candidate.prob >= ENGLISH_LANGDETECT_THRESHOLD:
            return True
    return False


def filter_english(reviews: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """
    Drop reviews that are not confidently English.

    Returns (kept, dropped_count).
    """
    kept = []
    dropped = 0
    for r in reviews:
        text = (r.get("review_text") or "").strip()
        if len(text) < MIN_REVIEW_CHARS:
            dropped += 1
            continue
        if not is_probably_english(text):
            dropped += 1
            continue
        kept.append(r)
    return kept, dropped


# ---------------------------------------------------------------------------
# Stage 3: Sentence splitting
# ---------------------------------------------------------------------------
def split_to_sentences(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Split each review into sentences. Each sentence becomes its own record
    that carries the parent review's id and metadata so we can trace
    predictions back to source if needed.

    Output record shape:
        {
            "review_id": str,
            "sentence_id": int,
            "text": str,
            "doc": <spaCy Doc>,        # cached for downstream matching
            "voted_up": bool,           # passed through for evaluation
            "created_at": str | None,
        }
    """
    nlp = _get_nlp()
    out: list[dict[str, Any]] = []

    raw_texts = [(r.get("review_text") or "").strip() for r in reviews]

    for review, doc in zip(reviews, nlp.pipe(raw_texts, batch_size=64)):
        review_id = str(review.get("recommendationid") or "")
        for idx, sent in enumerate(doc.sents):
            sent_text = sent.text.strip()
            if not sent_text:
                continue
            token_count = sum(1 for t in sent if not t.is_space)
            if token_count < MIN_SENTENCE_TOKENS or token_count > MAX_SENTENCE_TOKENS:
                continue
            out.append({
                "review_id": review_id,
                "sentence_id": idx,
                "text": sent_text,
                "doc": sent.as_doc(),
                "voted_up": str(review.get("voted_up", "")).lower() == "true",
                "created_at": review.get("created_at"),
            })
    return out


# ---------------------------------------------------------------------------
# Stage 4: Aspect matching
# ---------------------------------------------------------------------------
def _build_lookup(aspects: dict[str, list[str]]) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """
    Split aspect synonyms into two lookup tables:
        - single_token_lookup : canonical name -> set of lemmatized single tokens
        - multi_token_lookup  : canonical name -> list of lowercase phrases

    Single tokens are matched via lemma equality. Multi-word phrases are
    matched by lowercase substring on the raw sentence text.
    """
    nlp = _get_nlp()
    single_token: dict[str, set[str]] = {}
    multi_token: dict[str, list[str]] = {}

    for canonical, surface_forms in aspects.items():
        single: set[str] = set()
        multi: list[str] = []
        for form in surface_forms:
            stripped = form.strip().lower()
            if " " in stripped or "-" in stripped:
                multi.append(stripped)
            else:
                # Lemmatize the single token form
                doc = nlp(stripped)
                if len(doc) >= 1:
                    single.add(doc[0].lemma_.lower())
        single_token[canonical] = single
        multi_token[canonical] = multi

    return single_token, multi_token


def match_aspects(
    sentences: list[dict[str, Any]],
    aspects: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """
    For each sentence, return one record per matched aspect.

    Output record shape:
        {
            "review_id": str,
            "sentence_id": int,
            "text": str,
            "aspect": str,            # canonical aspect name
            "voted_up": bool,
            "created_at": str | None,
        }
    """
    single_lookup, multi_lookup = _build_lookup(aspects)
    matched: list[dict[str, Any]] = []

    for sent in sentences:
        doc = sent["doc"]
        text_lower = sent["text"].lower()
        sentence_lemmas = {tok.lemma_.lower() for tok in doc if not tok.is_punct}

        for canonical, single_set in single_lookup.items():
            hit = False
            if single_set & sentence_lemmas:
                hit = True
            else:
                for phrase in multi_lookup[canonical]:
                    if phrase in text_lower:
                        hit = True
                        break
            if hit:
                matched.append({
                    "review_id": sent["review_id"],
                    "sentence_id": sent["sentence_id"],
                    "text": sent["text"],
                    "aspect": canonical,
                    "voted_up": sent["voted_up"],
                    "created_at": sent["created_at"],
                })
    return matched


def residual_sentences(
    sentences: list[dict[str, Any]],
    matched: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return the sentences that did not match any predefined aspect.
    These are the input to BERTopic.
    """
    matched_keys = {(m["review_id"], m["sentence_id"]) for m in matched}
    return [
        s for s in sentences
        if (s["review_id"], s["sentence_id"]) not in matched_keys
    ]


# ---------------------------------------------------------------------------
# Stage 5: Sentiment
# ---------------------------------------------------------------------------
def load_sentiment_classifier(model_path: str = SENTIMENT_MODEL):
    """Load the DeBERTa ABSA pipeline. Cached by HuggingFace internally."""
    print(f"Loading sentiment model: {model_path}")
    t0 = time.time()
    classifier = pipeline(
        "text-classification",
        model=model_path,
        tokenizer=model_path,
        top_k=None,
    )
    print(f"  loaded in {time.time() - t0:.1f}s")
    return classifier


def run_sentiment(
    pair_records: list[dict[str, Any]],
    classifier,
    batch_size: int = SENTIMENT_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """
    Run DeBERTa on each (sentence, aspect) pair and attach the prediction.

    Each input record must contain at least 'text' and 'aspect'. Output
    records add 'label', 'confidence', and 'scores' (full distribution).
    """
    if not pair_records:
        return []

    inputs = [{"text": r["text"], "text_pair": r["aspect"]} for r in pair_records]

    enriched: list[dict[str, Any]] = []
    cursor = 0
    total = len(inputs)
    print(f"Running sentiment on {total} (sentence, aspect) pairs...")
    t0 = time.time()

    for output in classifier(inputs, batch_size=batch_size, top_k=None):
        # output is a list of {"label": ..., "score": ...} dicts
        if isinstance(output, dict):
            output = [output]
        score_map = {item["label"]: round(float(item["score"]), 4) for item in output}
        best = max(output, key=lambda item: item["score"])
        rec = dict(pair_records[cursor])
        rec["label"] = best["label"]
        rec["confidence"] = round(float(best["score"]), 4)
        rec["scores"] = score_map
        enriched.append(rec)
        cursor += 1
        if cursor % 500 == 0:
            elapsed = time.time() - t0
            rate = cursor / elapsed if elapsed > 0 else 0.0
            print(f"  {cursor}/{total}  ({rate:.1f} pairs/s)")

    print(f"  done in {time.time() - t0:.1f}s")
    return enriched


# ---------------------------------------------------------------------------
# Stage 6: Aggregation
# ---------------------------------------------------------------------------
def aggregate(
    enriched: list[dict[str, Any]],
    source_label: str = "predefined",
    extra_fields: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Roll up per-aspect statistics for the dashboard.

    The 'extra_fields' argument lets the BERTopic stage attach its own
    cluster-level metadata (keywords, cluster_id) without complicating
    the predefined-aspect path.

    Output record shape (one per aspect):
        {
            "aspect": str,
            "source": "predefined" | "bertopic",
            "mention_count": int,
            "sentiment": {
                "positive": {"count": int, "pct": float, "weighted_pct": float},
                "neutral":  {...},
                "negative": {...}
            },
            "average_confidence": float,
            "net_score": float,            # weighted_pct_pos - weighted_pct_neg, in [-1, 1]
            "examples": {
                "positive": list[str], "neutral": list[str], "negative": list[str]
            },
            ... any extra_fields[aspect] ...
        }
    """
    by_aspect: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in enriched:
        by_aspect[r["aspect"]].append(r)

    out: list[dict[str, Any]] = []
    for aspect, records in by_aspect.items():
        total = len(records)
        counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
        weighted = {"Positive": 0.0, "Neutral": 0.0, "Negative": 0.0}
        conf_sum = 0.0
        examples = {"Positive": [], "Neutral": [], "Negative": []}

        # Sort records by confidence descending so example selection
        # picks the most confident examples per class.
        for r in sorted(records, key=lambda x: -x["confidence"]):
            counts[r["label"]] += 1
            weighted[r["label"]] += r["confidence"]
            conf_sum += r["confidence"]
            if len(examples[r["label"]]) < EXAMPLES_PER_SENTIMENT:
                examples[r["label"]].append(r["text"])

        weighted_total = sum(weighted.values()) or 1.0
        rec = {
            "aspect": aspect,
            "source": source_label,
            "mention_count": total,
            "sentiment": {
                "positive": {
                    "count": counts["Positive"],
                    "pct": round(counts["Positive"] / total * 100, 1),
                    "weighted_pct": round(weighted["Positive"] / weighted_total * 100, 1),
                },
                "neutral": {
                    "count": counts["Neutral"],
                    "pct": round(counts["Neutral"] / total * 100, 1),
                    "weighted_pct": round(weighted["Neutral"] / weighted_total * 100, 1),
                },
                "negative": {
                    "count": counts["Negative"],
                    "pct": round(counts["Negative"] / total * 100, 1),
                    "weighted_pct": round(weighted["Negative"] / weighted_total * 100, 1),
                },
            },
            "average_confidence": round(conf_sum / total, 4),
            "net_score": round(
                (weighted["Positive"] - weighted["Negative"]) / weighted_total, 4
            ),
            "examples": {
                "positive": examples["Positive"],
                "neutral": examples["Neutral"],
                "negative": examples["Negative"],
            },
        }
        if extra_fields and aspect in extra_fields:
            rec.update(extra_fields[aspect])
        out.append(rec)

    # Sort by mention count descending so the dashboard sees prominent
    # aspects first.
    out.sort(key=lambda r: -r["mention_count"])
    return out
