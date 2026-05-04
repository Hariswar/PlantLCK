from data import downloading_gameReviews
import pandas as pd
import spacy

dataset = downloading_gameReviews()
data = pd.read_csv(dataset)
nlp = spacy.load("en_core_web_sm")
data_format = 'review_text'

def cleaning_reviews(data):
  data = data.dropna(subset=[data_format])
  data[data_format] = data[data_format].str.lower()
  data = data.drop_duplicates(subset=[data_format])
  data[data_format] = data[data_format].str.strip()
  data = data[data[data_format] != '']
  return data

print(cleaning_reviews(data))




