FROM python:3.14
WORKDIR ./app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# Expose default uvicorn port and run the app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]