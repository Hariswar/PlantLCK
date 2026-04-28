from data import steam_reviews_download
import pandas as pd
import spacy

dataset = steam_reviews_download()
df = pd.read_csv(dataset)
nlp = spacy.load("en_core_web_sm")