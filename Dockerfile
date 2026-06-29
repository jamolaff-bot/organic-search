FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Ingest data then start server
CMD ["sh", "-c", "python ingest.py && python app.py"]
