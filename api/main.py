import json
from typing import Any
from urllib.error import URLError
from urllib.parse import quote_plus
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PlantLck Backend API")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


def _fetch_json(url: str) -> dict[str, Any]:
	try:
		with urlopen(url, timeout=10) as response:
			return json.loads(response.read().decode("utf-8"))
	except URLError as exc:
		raise HTTPException(status_code=502, detail="Steam API is unavailable") from exc


@app.get("/search")
def search_games(query: str = Query(..., min_length=1, max_length=100)) -> dict[str, Any]:
	cleaned_query = query.strip()
	if not cleaned_query:
		raise HTTPException(status_code=400, detail="Query cannot be empty")

	is_six_digit_game_id = cleaned_query.isdigit() and len(cleaned_query) == 6

	if is_six_digit_game_id:
		details_url = (
			"https://store.steampowered.com/api/appdetails"
			f"?appids={cleaned_query}&cc=us&l=english"
		)
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

	search_url = (
		"https://store.steampowered.com/api/storesearch/"
		f"?term={quote_plus(cleaned_query)}&l=english&cc=us"
	)
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

