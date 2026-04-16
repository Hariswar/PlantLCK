import csv
import io
import time
from typing import Any, Optional

import requests
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
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


def fetch_steam_reviews(
    app_id: int,
    limit: Optional[int] = Query(100, description="Max reviews to fetch. Leave empty/null for ALL reviews."),
) -> list[dict]:
    """Scrape the first {limit} Steam reviews for the provided app ID (if limit is None, scrape all reviews)"""
    url = f"https://store.steampowered.com/appreviews/{app_id}?json=1"
    all_reviews = []
    cursor = "*"

    while True:
        batch_size = 100
        if limit is not None:
            # Only ask for the amount we still need
            remaining = limit - len(all_reviews)
            if remaining <= 0:
                break
            batch_size = min(100, remaining)

        # Steam API parameters (just get everything)
        params = {
            "filter": "recent",
            "language": "english",
            "purchase_type": "all",
            "num_per_page": batch_size,
            "cursor": cursor,
        }

        # Send the request
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(f"Failed to fetch data. Status Code: {response.status_code}")
            break
        data = response.json()

        # Extract reviews
        batch_reviews = data.get("reviews", [])

        # If the batch is empty, there are no more reviews left to fetch
        if not batch_reviews:
            break

        # Strip newlines/carriage returns and store data
        for review in batch_reviews:
            review["review"] = strip_review_text(review.get("review"))
        all_reviews.extend(batch_reviews)

        # Grab the cursor for the next request
        next_cursor = data.get("cursor")

        # If cursor doesn't update, it's done
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

        time.sleep(0.5)

    return all_reviews


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
        author = r.get("author", {})
        writer.writerow(
            [
                r.get("recommendationid"),
                author.get("steamid"),
                author.get("playtime_forever"),
                r.get("voted_up"),
                r.get("votes_up"),
                r.get("review"),
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
