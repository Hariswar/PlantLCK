from pathlib import Path
import requests

url = "http://localhost:8000"
cyberpunk_2077ID = 1091500 
limit_of_the_game_reviews = 1000 #So, I just set the limit to 1000 for the reviews but we can change it to how many review wen want to get. 

# Included a function for downloading reviews from the backend API
def downloading_gameReviews():
  url_link = f"{url}/reviews/{cyberpunk_2077ID}" + (f"?limit={limit_of_the_game_reviews}")

  output = requests.get(url_link)
  output.raise_for_status()

  output_data = Path("Cyberpunk_2077_reviews.csv")
  stored_info = output.content
  output_data.write_bytes(stored_info)
  return output_data



