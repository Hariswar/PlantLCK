from data import downloading_gameReviews
import pandas as pd
import spacy

dataset = downloading_gameReviews()
data = pd.read_csv(dataset)
nlp = spacy.load("en_core_web_sm")
data_format = 'review_text'

def cleaning_reviews(data):
  punctuations = r'[^a-zA-Z0-9\s]'
  symbol_check = r'@[A-Za-z0-9_]+'
  data = data.dropna(subset=[data_format])
  data[data_format] = data[data_format].str.lower()
  data = data.drop_duplicates(subset=[data_format])
  data[data_format] = data[data_format].str.strip()
  data[data_format] = data[data_format].str.replace(symbol_check, '', regex=True)
  data[data_format] = data[data_format].str.replace(punctuations, '', regex=True)
  data = data[data[data_format] != '']
  return data

print(cleaning_reviews(data))




