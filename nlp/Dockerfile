FROM python:3.14
WORKDIR ./app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt && \
    python -m spacy download en_core_web_sm && \
    pip cache purge
