FROM python:3.14
WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# Copy the rest of the source
COPY . ./

# Expose default uvicorn port and run the app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]