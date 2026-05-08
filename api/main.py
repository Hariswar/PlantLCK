import csv
import io
import threading
import time
from datetime import date, datetime, timezone
from uuid import uuid4
from typing import Any, Optional

import requests
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from urllib.parse import quote_plus


app = FastAPI(title="PlantLck Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check():
    """Just ping the backend to make sure it's working"""
    return {"status": "Backend is alive and kicking!"}


class ReviewJobRequest(BaseModel):
    app_id: int = Field(..., ge=1)
    limit: int = Field(500, ge=1, le=5000)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    language: str = Field("english", min_length=1, max_length=32)
    purchase_type: str = Field("all", min_length=1, max_length=32)


review_jobs: dict[str, dict[str, Any]] = {}
review_jobs_lock = threading.Lock()


def _utc_start_of_day(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed_date = date.fromisoformat(value)
    return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=timezone.utc)


def _utc_end_of_day(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed_date = date.fromisoformat(value)
    return datetime(parsed_date.year, parsed_date.month, parsed_date.day, 23, 59, 59, tzinfo=timezone.utc)


def _normalize_review(review: dict[str, Any]) -> dict[str, Any]:
    timestamp_created = review.get("timestamp_created")
    created_at = None
    if isinstance(timestamp_created, (int, float)):
        created_at = datetime.fromtimestamp(timestamp_created, tz=timezone.utc).isoformat()

    author = review.get("author", {})
    return {
        "recommendationid": review.get("recommendationid"),
        "steamid": author.get("steamid"),
        "playtime_forever_minutes": author.get("playtime_forever"),
        "voted_up": bool(review.get("voted_up")),
        "votes_up": review.get("votes_up"),
        "review_text": strip_review_text(review.get("review")),
        "created_at": created_at,
        "language": review.get("language"),
        "steam_purchase": review.get("steam_purchase"),
    }


def _matches_review_filters(
    review: dict[str, Any],
    language: str,
    purchase_type: str,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> bool:
    if language != "all" and (review.get("language") or "").lower() != language.lower():
        return False

    if purchase_type == "steam" and not review.get("steam_purchase"):
        return False
    if purchase_type == "non_steam" and review.get("steam_purchase"):
        return False

    created_at = review.get("created_at")
    if created_at:
        parsed_created_at = datetime.fromisoformat(created_at)
        if date_from and parsed_created_at < date_from:
            return False
        if date_to and parsed_created_at > date_to:
            return False

    return True


def _build_review_request_params(batch_size: int, cursor: str, language: str, purchase_type: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "filter": "recent",
        "purchase_type": purchase_type,
        "num_per_page": batch_size,
        "cursor": cursor,
    }
    if language != "all":
        params["language"] = language
    return params


def _collect_reviews_with_progress(
    app_id: int,
    limit: int,
    language: str,
    purchase_type: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    progress_callback: Optional[Any] = None,
) -> list[dict[str, Any]]:
    url = f"https://store.steampowered.com/appreviews/{app_id}?json=1"
    all_reviews: list[dict[str, Any]] = []
    cursor = "*"
    fetched_reviews = 0
    min_created_at = _utc_start_of_day(date_from)
    max_created_at = _utc_end_of_day(date_to)

    while True:
        remaining = limit - fetched_reviews
        if remaining <= 0:
            break

        batch_size = min(100, remaining)
        response = requests.get(
            url,
            params=_build_review_request_params(batch_size, cursor, language, purchase_type),
            timeout=20,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Steam review endpoint is unavailable")

        data = response.json()
        batch_reviews = data.get("reviews", [])
        if not batch_reviews:
            break

        fetched_reviews += len(batch_reviews)

        for review in batch_reviews:
            normalized_review = _normalize_review(review)
            if _matches_review_filters(normalized_review, language, purchase_type, min_created_at, max_created_at):
                all_reviews.append(normalized_review)

        if progress_callback:
            progress_callback(fetched_reviews, len(all_reviews), limit)

        next_cursor = data.get("cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

        time.sleep(0.5)

    return all_reviews


def _update_review_job(job_id: str, **changes: Any) -> None:
    with review_jobs_lock:
        job = review_jobs.get(job_id)
        if job is None:
            return
        job.update(changes)


def _run_review_job(job_id: str) -> None:
    with review_jobs_lock:
        job = review_jobs.get(job_id)

    if job is None:
        return

    _update_review_job(job_id, status="running", error=None)

    try:

        def update_progress(fetched_count: int, matched_count: int, limit: int) -> None:
            with review_jobs_lock:
                current_job = review_jobs.get(job_id)
                if current_job is None:
                    return

                progress_percent = 100 if limit <= 0 else min(100, (fetched_count / limit) * 100)
                current_job.update(
                    {
                        "fetched_count": fetched_count,
                        "matched_count": matched_count,
                        "progress_percent": progress_percent,
                    }
                )

        reviews = _collect_reviews_with_progress(
            app_id=job["app_id"],
            limit=job["limit"],
            language=job["language"],
            purchase_type=job["purchase_type"],
            date_from=job.get("date_from"),
            date_to=job.get("date_to"),
            progress_callback=update_progress,
        )

        with review_jobs_lock:
            current_job = review_jobs.get(job_id)
            fetched_count = current_job["fetched_count"] if current_job is not None else job["limit"]

        _update_review_job(
            job_id,
            status="completed",
            progress_percent=100,
            fetched_count=fetched_count,
            matched_count=len(reviews),
            reviews=reviews,
        )
    except HTTPException as exc:
        _update_review_job(job_id, status="failed", error=exc.detail)
    except Exception:
        _update_review_job(job_id, status="failed", error="Unexpected failure while fetching reviews")


def fetch_steam_reviews(
    app_id: int,
    limit: Optional[int] = Query(100, description="Max reviews to fetch. Leave empty/null for ALL reviews."),
) -> list[dict]:
    """Scrape the first {limit} Steam reviews for the provided app ID (if limit is None, scrape all reviews)"""
    reviews = _collect_reviews_with_progress(
        app_id=app_id,
        limit=limit if limit is not None else 5000,
        language="english",
        purchase_type="all",
    )
    return reviews


@app.post("/reviews/jobs")
def create_review_job(request: ReviewJobRequest) -> dict[str, Any]:
    job_id = uuid4().hex
    job = {
        "job_id": job_id,
        "app_id": request.app_id,
        "limit": request.limit,
        "status": "queued",
        "progress_percent": 0.0,
        "fetched_count": 0,
        "matched_count": 0,
        "total_requested": request.limit,
        "error": None,
        "reviews": [],
        "date_from": request.date_from,
        "date_to": request.date_to,
        "language": request.language,
        "purchase_type": request.purchase_type,
    }

    with review_jobs_lock:
        review_jobs[job_id] = job

    threading.Thread(target=_run_review_job, args=(job_id,), daemon=True).start()

    return {"job_id": job_id, "status": job["status"]}


@app.get("/reviews/jobs/{job_id}")
def get_review_job_status(job_id: str) -> dict[str, Any]:
    with review_jobs_lock:
        job = review_jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Review job not found")

    return {
        "job_id": job["job_id"],
        "app_id": job["app_id"],
        "status": job["status"],
        "progress_percent": job["progress_percent"],
        "fetched_count": job["fetched_count"],
        "matched_count": job["matched_count"],
        "total_requested": job["total_requested"],
        "error": job["error"],
    }


@app.get("/reviews/jobs/{job_id}/result")
def get_review_job_result(job_id: str) -> dict[str, Any]:
    with review_jobs_lock:
        job = review_jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Review job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail="Review job is not complete yet")

    return {
        "job_id": job["job_id"],
        "app_id": job["app_id"],
        "reviews": job["reviews"],
        "total_reviews": len(job["reviews"]),
        "filters": {
            "dateFrom": job.get("date_from") or "",
            "dateTo": job.get("date_to") or "",
            "language": job["language"],
            "purchaseType": job["purchase_type"],
            "limit": job["limit"],
        },
    }


@app.get("/reviews/{app_id}")
def get_steam_reviews_csv(app_id: int, limit: Optional[int] = Query(100, description="Max reviews to fetch.")):
    """(Wrapper for FastAPI) Get Steam reviews and pack into a downloadable CSV"""
    reviews = fetch_steam_reviews(app_id, limit)

    # Create an in-memory string buffer to hold the CSV data
    output = io.StringIO()
    writer = csv.writer(output)

    # Write the column headers
    writer.writerow(
        [
            "recommendationid",
            "steamid",
            "playtime_forever_minutes",
            "voted_up",
            "votes_up",
            "review_text",
        ]
    )

    # Write the data for each review
    for r in reviews:
        writer.writerow(
            [
                r.get("recommendationid"),
                r.get("steamid"),
                r.get("playtime_forever_minutes"),
                r.get("voted_up"),
                r.get("votes_up"),
                r.get("review_text"),
            ]
        )

    # Return the data as a downloadable file
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=steam_reviews_{app_id}.csv"},
    )


def strip_review_text(review: str) -> str:
    if not review:
        return ""
    return review.replace("\r", " ").replace("\n", " ").strip()


def _fetch_json(url: str) -> dict[str, Any]:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Steam API is unavailable") from exc


@app.get("/search")
def search_games(query: str = Query(..., min_length=1, max_length=100)) -> dict[str, Any]:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    is_six_digit_game_id = cleaned_query.isdigit() and len(cleaned_query) == 6

    if is_six_digit_game_id:
        details_url = f"https://store.steampowered.com/api/appdetails?appids={cleaned_query}&cc=us&l=english"
        details_payload = _fetch_json(details_url)
        game_block = details_payload.get(cleaned_query)

        if not game_block or not game_block.get("success"):
            raise HTTPException(status_code=404, detail="No game found for this ID")

        data = game_block.get("data", {})
        return {
            "query": cleaned_query,
            "results": [
                {
                    "appid": data.get("steam_appid", int(cleaned_query)),
                    "name": data.get("name", "Unknown Game"),
                    "image": data.get("header_image"),
                }
            ],
        }

    search_url = f"https://store.steampowered.com/api/storesearch/?term={quote_plus(cleaned_query)}&l=english&cc=us"
    search_payload = _fetch_json(search_url)
    raw_items = search_payload.get("items", [])

    results = [
        {
            "appid": item.get("id"),
            "name": item.get("name", "Unknown Game"),
            "image": item.get("tiny_image"),
        }
        for item in raw_items
    ]

    return {
        "query": cleaned_query,
        "results": results,
    }
