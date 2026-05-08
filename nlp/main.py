import sys
import threading
import importlib.util
from pathlib import Path
from uuid import uuid4
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

# Sentiment code is now in the nlp folder itself
SENTIMENT_PATH = Path(__file__).parent
if SENTIMENT_PATH.exists() and str(SENTIMENT_PATH) not in sys.path:
    sys.path.insert(0, str(SENTIMENT_PATH))


def _load_absa_modules():
    """Dynamically load ABSA modules using importlib for better reliability."""
    modules = {}
    try:
        # Try standard import first
        import absa_config
        import absa_pipeline
        from absa_config import GAME_NAMES, SENTIMENT_MODEL, aspects_for_app
        from absa_pipeline import (
            filter_english,
            load_sentiment_classifier,
            match_aspects,
            residual_sentences,
            run_sentiment,
            split_to_sentences,
            aggregate,
        )

        modules["absa_config"] = absa_config
        modules["GAME_NAMES"] = GAME_NAMES
        modules["SENTIMENT_MODEL"] = SENTIMENT_MODEL
        modules["aspects_for_app"] = aspects_for_app
        modules["absa_pipeline"] = absa_pipeline
        modules["filter_english"] = filter_english
        modules["load_sentiment_classifier"] = load_sentiment_classifier
        modules["match_aspects"] = match_aspects
        modules["residual_sentences"] = residual_sentences
        modules["run_sentiment"] = run_sentiment
        modules["split_to_sentences"] = split_to_sentences
        modules["aggregate"] = aggregate
    except ImportError as e:
        # Fallback: try to load using importlib
        print(f"Standard import failed: {e}. Trying importlib fallback...")
        for module_name in ["absa_config", "absa_pipeline"]:
            spec = importlib.util.spec_from_file_location(module_name, SENTIMENT_PATH / f"{module_name}.py")
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = mod
                spec.loader.exec_module(mod)
                modules[module_name] = mod
        # Try loading functions after modules are loaded
        try:
            from absa_config import GAME_NAMES, SENTIMENT_MODEL, aspects_for_app
            from absa_pipeline import (
                filter_english,
                load_sentiment_classifier,
                match_aspects,
                residual_sentences,
                run_sentiment,
                split_to_sentences,
                aggregate,
            )

            modules["GAME_NAMES"] = GAME_NAMES
            modules["SENTIMENT_MODEL"] = SENTIMENT_MODEL
            modules["aspects_for_app"] = aspects_for_app
            modules["filter_english"] = filter_english
            modules["load_sentiment_classifier"] = load_sentiment_classifier
            modules["match_aspects"] = match_aspects
            modules["residual_sentences"] = residual_sentences
            modules["run_sentiment"] = run_sentiment
            modules["split_to_sentences"] = split_to_sentences
            modules["aggregate"] = aggregate
        except ImportError as e2:
            print(f"Importlib fallback also failed: {e2}")
            modules["error"] = str(e2)
    return modules


app = FastAPI(title="PlantLck NLP API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check():
    """Health check endpoint for NLP service"""
    return {"status": "NLP service is alive and kicking!"}


class AnalysisRequest(BaseModel):
    """Request model for sentiment analysis"""

    app_id: int = Field(..., ge=1)
    reviews: list[dict[str, Any]] = Field(..., min_items=1)


analysis_jobs: dict[str, dict[str, Any]] = {}
analysis_jobs_lock = threading.Lock()
analysis_cache: dict[str, dict[str, Any]] = {}  # Cache key: f"{app_id}_{date_from}_{date_to}"


def _update_analysis_job(job_id: str, **changes: Any) -> None:
    with analysis_jobs_lock:
        job = analysis_jobs.get(job_id)
        if job is None:
            return
        job.update(changes)


def _run_analysis_job(job_id: str, reviews: list[dict[str, Any]], app_id: int) -> None:
    with analysis_jobs_lock:
        job = analysis_jobs.get(job_id)

    if job is None:
        return

    _update_analysis_job(job_id, status="running", error=None, progress_percent=5)

    try:
        # Load ABSA modules robustly
        absa = _load_absa_modules()
        if "error" in absa:
            raise ImportError(f"Failed to load ABSA modules: {absa['error']}")

        GAME_NAMES = absa["GAME_NAMES"]
        SENTIMENT_MODEL = absa["SENTIMENT_MODEL"]
        aspects_for_app = absa["aspects_for_app"]
        filter_english = absa["filter_english"]
        load_sentiment_classifier = absa["load_sentiment_classifier"]
        match_aspects = absa["match_aspects"]
        residual_sentences = absa["residual_sentences"]
        run_sentiment = absa["run_sentiment"]
        split_to_sentences = absa["split_to_sentences"]
        aggregate = absa["aggregate"]

        # Process reviews
        _update_analysis_job(job_id, progress_percent=20, status_message="Processing reviews...")

        # Filter to English reviews
        reviews_kept, dropped = filter_english(reviews)

        if not reviews_kept:
            _update_analysis_job(
                job_id,
                status="completed",
                progress_percent=100,
                analysis_report={
                    "metadata": {
                        "app_id": app_id,
                        "reviews_loaded": len(reviews),
                        "reviews_kept_after_english_filter": 0,
                        "reviews_dropped_non_english_or_short": dropped,
                        "error": "No English reviews found",
                    },
                    "predefined_aspects": [],
                    "discovered_topics": [],
                },
            )
            return

        # Split to sentences
        _update_analysis_job(job_id, progress_percent=30, status_message="Splitting sentences...")
        sentences = split_to_sentences(reviews_kept)

        # Match aspects
        _update_analysis_job(job_id, progress_percent=40, status_message="Matching aspects...")
        aspects = aspects_for_app(app_id)
        matched = match_aspects(sentences, aspects)

        # BERTopic on residual
        discovered_pairs = []
        cluster_metadata = {}
        try:
            _update_analysis_job(job_id, progress_percent=50, status_message="Discovering topics...")
            residual = residual_sentences(sentences, matched)
            # Dynamically load discover_topics
            discover_spec = importlib.util.spec_from_file_location("absa_topics", SENTIMENT_PATH / "absa_topics.py")
            if discover_spec and discover_spec.loader:
                discover_mod = importlib.util.module_from_spec(discover_spec)
                sys.modules["absa_topics"] = discover_mod
                discover_spec.loader.exec_module(discover_mod)
                discover_topics = discover_mod.discover_topics
            else:
                from absa_topics import discover_topics

            discovered_pairs, cluster_metadata = discover_topics(residual)
        except Exception as e:
            print(f"Topic discovery failed (non-fatal): {e}")
            cluster_metadata = {}

        # Sentiment analysis
        _update_analysis_job(job_id, progress_percent=65, status_message="Analyzing sentiment...")
        classifier = load_sentiment_classifier(SENTIMENT_MODEL)
        matched_enriched = run_sentiment(matched, classifier)
        discovered_enriched = run_sentiment(discovered_pairs, classifier) if discovered_pairs else []

        # Aggregation
        _update_analysis_job(job_id, progress_percent=85, status_message="Aggregating results...")
        predefined_summary = aggregate(matched_enriched, source_label="predefined")
        discovered_summary = aggregate(
            discovered_enriched,
            source_label="bertopic",
            extra_fields=cluster_metadata,
        )

        # Assemble report
        report = {
            "metadata": {
                "app_id": app_id,
                "game_name": GAME_NAMES.get(app_id, "Unknown"),
                "model": SENTIMENT_MODEL,
                "reviews_loaded": len(reviews),
                "reviews_kept_after_english_filter": len(reviews_kept),
                "reviews_dropped_non_english_or_short": dropped,
                "sentences_analyzed": len(sentences),
                "predefined_pairs": len(matched_enriched),
                "discovered_pairs": len(discovered_enriched),
                "discovered_topic_count": len(cluster_metadata),
                "bertopic_skipped": len(cluster_metadata) == 0,
            },
            "predefined_aspects": predefined_summary,
            "discovered_topics": discovered_summary,
        }

        _update_analysis_job(
            job_id,
            status="completed",
            progress_percent=100,
            analysis_report=report,
            status_message="Analysis complete",
        )

    except ImportError as e:
        _update_analysis_job(job_id, status="failed", error=f"ABSA dependencies not installed: {str(e)}")
    except Exception as e:
        _update_analysis_job(job_id, status="failed", error=f"Unexpected failure: {str(e)}")


@app.post("/analyze")
def analyze_reviews(request: AnalysisRequest) -> dict[str, Any]:
    """
    Analyze reviews for sentiment using the ABSA pipeline.
    This endpoint expects an array of review dictionaries with fields:
    - recommendationid, steamid, playtime_forever_minutes, voted_up,
      votes_up, review_text, created_at, language, steam_purchase
    """
    job_id = uuid4().hex
    job = {
        "job_id": job_id,
        "app_id": request.app_id,
        "status": "queued",
        "progress_percent": 0.0,
        "status_message": "Queued",
        "error": None,
        "analysis_report": None,
    }

    with analysis_jobs_lock:
        analysis_jobs[job_id] = job

    threading.Thread(
        target=_run_analysis_job,
        args=(job_id, request.reviews, request.app_id),
        daemon=True,
    ).start()

    return {"job_id": job_id, "status": job["status"]}


@app.get("/analyze/{job_id}")
def get_analysis_status(job_id: str) -> dict[str, Any]:
    """Get the status of an analysis job"""
    with analysis_jobs_lock:
        job = analysis_jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    return {
        "job_id": job["job_id"],
        "app_id": job["app_id"],
        "status": job["status"],
        "progress_percent": job["progress_percent"],
        "status_message": job.get("status_message", ""),
        "error": job["error"],
    }


@app.get("/analyze/{job_id}/result")
def get_analysis_result(job_id: str) -> dict[str, Any]:
    """Get the analysis result from a completed job"""
    with analysis_jobs_lock:
        job = analysis_jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="Analysis job is not complete yet")
    if job["error"]:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {job['error']}")

    return job["analysis_report"]
