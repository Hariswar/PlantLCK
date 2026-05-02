"""
BERTopic Discovery
===================
Run BERTopic on the residual sentences (those that did not match any
predefined aspect) to surface emergent themes that the curated taxonomy
does not cover.

The output of this module is shaped to feed directly into the same
sentiment + aggregation flow used for predefined aspects, so the final
report is uniform.

Design notes:
    - The aspect string passed to DeBERTa for each cluster is the top
      keyword from BERTopic's c-TF-IDF representation. Single keywords
      work better than phrases because DeBERTa was trained on aspect
      terms, not topic descriptions.
    - The cluster's full keyword list is preserved separately so the
      dashboard can render a richer label than the single keyword.
    - HDBSCAN's noise cluster (-1) is dropped.
    - MIN_TOPIC_SIZE in the config controls how aggressively small
      meme clusters are filtered out.
"""

from __future__ import annotations

from typing import Any

from absa_config import (
    EMBEDDING_MODEL,
    MIN_TOPIC_SIZE,
    TOP_KEYWORDS_PER_TOPIC,
)


def discover_topics(
    residual: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """
    Run BERTopic on the residual sentences.

    Parameters
    ----------
    residual : list[dict]
        Sentence records that did not match any predefined aspect.
        Each must contain at least 'review_id', 'sentence_id', 'text',
        'voted_up', and 'created_at'.

    Returns
    -------
    pair_records : list[dict]
        One record per (sentence, discovered aspect) ready for the
        sentiment stage. Same shape as predefined matches, with the
        addition of 'cluster_id'.
    cluster_metadata : dict[str, dict]
        Keyed by canonical aspect name (the top keyword). Each entry
        contains 'keywords' and 'cluster_id', for attaching to the
        aggregate output.
    """
    # Imports are local so users who pass --skip-bertopic do not need
    # umap, hdbscan, or sentence-transformers installed at all.
    from bertopic import BERTopic
    from sentence_transformers import SentenceTransformer

    if len(residual) < MIN_TOPIC_SIZE * 2:
        # Not enough data for meaningful clustering.
        print(
            f"BERTopic skipped: only {len(residual)} residual sentences "
            f"(need at least {MIN_TOPIC_SIZE * 2})."
        )
        return [], {}

    print(f"Running BERTopic on {len(residual)} residual sentences...")
    texts = [r["text"] for r in residual]

    embedder = SentenceTransformer(EMBEDDING_MODEL)
    topic_model = BERTopic(
        embedding_model=embedder,
        min_topic_size=MIN_TOPIC_SIZE,
        verbose=False,
    )
    topics, _ = topic_model.fit_transform(texts)

    # Build cluster -> top keyword + keyword list
    cluster_info: dict[int, dict[str, Any]] = {}
    for cluster_id in set(topics):
        if cluster_id == -1:
            continue
        keyword_pairs = topic_model.get_topic(cluster_id) or []
        keywords = [kw for kw, _ in keyword_pairs[:TOP_KEYWORDS_PER_TOPIC]]
        if not keywords:
            continue
        top_keyword = keywords[0]
        cluster_info[cluster_id] = {
            "top_keyword": top_keyword,
            "keywords": keywords,
        }

    # Resolve label collisions: if two clusters share a top keyword,
    # disambiguate by appending the second keyword.
    seen_labels: set[str] = set()
    for cid, info in cluster_info.items():
        label = info["top_keyword"]
        if label in seen_labels and len(info["keywords"]) > 1:
            label = f"{info['keywords'][0]} / {info['keywords'][1]}"
        info["label"] = label
        seen_labels.add(label)

    # Build (sentence, aspect) records
    pair_records: list[dict[str, Any]] = []
    cluster_metadata: dict[str, dict[str, Any]] = {}

    for sentence, cluster_id in zip(residual, topics):
        if cluster_id == -1 or cluster_id not in cluster_info:
            continue
        info = cluster_info[cluster_id]
        label = info["label"]
        pair_records.append({
            "review_id": sentence["review_id"],
            "sentence_id": sentence["sentence_id"],
            "text": sentence["text"],
            "aspect": label,
            "voted_up": sentence["voted_up"],
            "created_at": sentence["created_at"],
        })
        if label not in cluster_metadata:
            cluster_metadata[label] = {
                "keywords": info["keywords"],
                "cluster_id": int(cluster_id),
            }

    print(
        f"  discovered {len(cluster_metadata)} topics covering "
        f"{len(pair_records)} sentences."
    )
    return pair_records, cluster_metadata
