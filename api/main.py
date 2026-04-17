from fastapi import FastAPI, Query, Response
from typing import Optional
import requests
import time
import csv
import io

app = FastAPI(title="PlantLck Backend API")

@app.get("/")
def health_check():
    """Just ping the backend to make sure it's working"""
    return {"status": "Backend is alive and kicking!"}

def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flattens nested dicts"""
    items = {}

    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v

    return items

def fetch_steam_reviews(
    app_id: int, 
    limit: Optional[int] = Query(100, description="Max reviews to fetch. Leave empty/null for ALL reviews.")
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
            "cursor": cursor
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
def get_steam_reviews_csv(
    app_id: int,
    limit: Optional[int] = Query(100)
):
    reviews = fetch_steam_reviews(app_id, limit)

    output = io.StringIO()

    # Flatten everything
    flat_rows = []
    for r in reviews:
        author = r.pop("author", {})
        r["author"] = author
        flat_rows.append(flatten_dict(r))

    # Generate columns
    fieldnames = sorted({key for row in flat_rows for key in row.keys()})

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for row in flat_rows:
        writer.writerow(row)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=steam_reviews_{app_id}.csv"}
    )


def strip_review_text(review: str) -> str:
    if not review:
        return ""
    return review.replace("\r", " ").replace("\n", " ").strip()

if __name__ == "__main__":
    game_id = 1091500
    reviews = fetch_steam_reviews(game_id, 1000)

    # flatten
    flat_rows = []
    for r in reviews:
        author = r.pop("author", {})
        r["author"] = author
        flat_rows.append(flatten_dict(r))

    # generate full schema dynamically
    fieldnames = sorted({k for row in flat_rows for k in row.keys()})

    with open(f"{game_id}_reviews.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)