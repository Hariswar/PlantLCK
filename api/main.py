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
        limit: Optional[int] = Query(100, description="Max reviews to fetch.")
):
    """(Wrapper for FastAPI) Get Steam reviews and pack into a downloadable CSV"""
    reviews = fetch_steam_reviews(app_id, limit)
    
    # Create an in-memory string buffer to hold the CSV data
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write the column headers
    writer.writerow([
        "recommendationid", 
        "steamid", 
        "playtime_forever_minutes", 
        "voted_up", 
        "votes_up", 
        "review_text"
    ])
    
    # Write the data for each review
    for r in reviews:
        author = r.get("author", {})
        writer.writerow([
            r.get("recommendationid"),
            author.get("steamid"),
            author.get("playtime_forever"),
            r.get("voted_up"),
            r.get("votes_up"),
            r.get("review")
        ])
        
    # Return the data as a downloadable file
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
    # Test the Steam API stuff
    game_id = 1353300
    reviews = fetch_steam_reviews(game_id, None)
    with open(f"{game_id}_reviews.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        # Headers
        writer.writerow([
            "recommendationid", 
            "steamid", 
            "playtime_forever_minutes", 
            "voted_up", 
            "votes_up", 
            "review_text"
        ])

        # Reviews
        for r in reviews:
            author = r.get("author", {})
            writer.writerow([
                r.get("recommendationid"),
                author.get("steamid"),
                author.get("playtime_forever"),
                r.get("voted_up"),
                r.get("votes_up"),
                strip_review_text(r.get("review"))
            ])